# ~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/Scripts/

# pro tip:
# sketch.isComputeDeferred = True

from collections import OrderedDict, namedtuple
import os.path
import traceback

import adsk
from adsk import core, fusion


_ATTR_GROUP = "GenDXF"

_TABLE_ID = 'exports-table'

_CELL_ID = '%s-%d'

_app = _ui = None

handlers = []

FaceExport = namedtuple('FaceExport', ('face', 'tempId', 'basename', 'status'))

EXPORT_STATUS = namedtuple(
    'ExportStatus',
    ('TENTATIVE', 'SELECTED', 'UNSELECTED')) \
    (1, 2, 3)


class ExecuteHandler(adsk.core.CommandEventHandler):
    def notify(self, args):
        args = adsk.core.CommandEventArgs.cast(args)
        inputs = args.command.commandInputs

        # sketches = rootComp.sketches
        # sketch = sketches.add()

        d = _ui.createFileDialog()
        d.isMultiSelectEnabled = False
        d.title = "Select output directory"
        d.filter = "Drawing Exchange Format (*.dxf)"
        d.filterIndex = 0
        rs = d.showSave()
        if rs == adsk.core.DialogResults.DialogOK:
            filename = d.filename
        else:
            return

        # yeah fuck "not overwriting built-ins" when they're stupid...
        dir = filename.rsplit(os.path.sep, 1)[0]

        table = inputs.itemById(_TABLE_ID)

        for row in range(1, table.rowCount):
            def input(_id):
                return inputs.itemById(_CELL_ID % (_id, row)).value

            temp_id, basename = map(input, ('temp-id', 'basename'))

            filename = input('filename') + input('ext')
            _ui.messageBox("Generating %s%s%s" % (dir, os.path.sep, filename))

        # if inputs.itemById('equilateral').value is True:
        #     _ui.messageBox("equilateral")
        # else:
        #     _ui.messageBox("not equilateral")

        adsk.terminate()


class CancelHandler(adsk.core.CommandEventHandler):
    def notify(self, args):
        adsk.terminate()


class ExportDialogHandler(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        args = adsk.core.CommandCreatedEventArgs.cast(args)
        cmd = args.command

        try:
            ok = mk_export_dialog(_app, cmd)
        except:
            _ui.messageBox("Error:\n%s" % (traceback.format_exc(),))
            ok = False

        if not ok:
            adsk.terminate()
            return False

        exe = ExecuteHandler()
        cmd.execute.add(exe)
        handlers.append(exe)

        cancel = CancelHandler()
        cmd.destroy.add(cancel)
        handlers.append(cancel)


class ExportsTable(adsk.core.InputChangedEventHandler):
    def __init__(self, inputs, selectionInputId):
        super(ExportsTable, self).__init__()
        self.inputs = inputs
        self.selectionInputId = selectionInputId
        self.exports = [] # type: list[FaceExport]
        self.table = self._mk_table() # type: core.TableCommandInput
        self._render_table()

    def _mk_table(self):
        table = self.inputs.addTableCommandInput(
            _TABLE_ID, "Output files", 4, "1:3:1:1")
        table.minimumVisibleRows = 3
        table.maximumVisibleRows = 8
        table.tablePresentationStyle = \
            adsk.core.TablePresentationStyles.itemBorderTablePresentationStyle
        return table

    def _render_table(self):
        self.table.clear()

        # header row
        i = self.inputs.addStringValueInput('h1', "", "Enable")
        i.isReadOnly = True
        assert self.table.addCommandInput(i, 0, 0, 0, 0)
        i = self.inputs.addStringValueInput('h2', "", "Filename")
        i.isReadOnly = True
        assert self.table.addCommandInput(i, 0, 1, 0, 1)

        # the actual export file list
        seen_filenames = set()
        for row, export in enumerate(self.exports, start=1):
            filename, n = export.basename, 1
            while filename in seen_filenames:
                n += 1
                filename = "%s (%d)" % (export.basename, n)
            seen_filenames.add(filename)

            # a couple hidden inputs
            for _id, value in (('basename', export.basename),
                               ('temp-id', str(export.tempId))):
                i = self.inputs.addStringValueInput(
                    _CELL_ID % (_id, row), "", value)
                i.isReadOnly = True
                i.isVisible = False

            if export.status != EXPORT_STATUS.TENTATIVE:
                i = self.inputs.addBoolValueInput(_CELL_ID % ('include', row), "", True)
                i.tooltip = "Whether to include the face in this export job"
                if export.status == EXPORT_STATUS.SELECTED:
                    i.value = True
                assert self.table.addCommandInput(i, row, 0, 0, 0)

            i = self.inputs.addStringValueInput(_CELL_ID % ('filename', row), "", filename)
            assert self.table.addCommandInput(i, row, 1, 0, 0)
            i = self.inputs.addStringValueInput(_CELL_ID % ('ext', row), "", ".dxf")
            i.isReadOnly = True
            assert self.table.addCommandInput(i, row, 2, 0, 0)

            i = self.inputs.addBoolValueInput(_CELL_ID % ('remove', row), "Remove", False)
            i.tooltip = "Remove the face from this list"
            assert self.table.addCommandInput(i, row, 3, 0, 0)

    def notify(self, args):
        args = adsk.core.InputChangedEventArgs.cast(args)
        # sample code:
        # inputs = args.firingEvent.sender.commandInputs
        # scaleInput = inputs.itemById('heightScale')
        if args.input.id == self.selectionInputId:
            select = args.input # type: core.SelectionCommandInput
            try:
                self._update_selected(select)
            except:
                _ui.messageBox("Failed:\n%s" % (traceback.format_exc(),))
        elif args.input.id == self.table.id:
            TODO

    def _update_selected(self, select):
        selected = {}
        for i in range(select.selectionCount):
            face = select.selection(i).entity # type: fusion.BRepFace
            selected[face.tempId] = face

        prune = set()
        for export in self.exports:
            try:
                selected.pop(export.tempId)
            except KeyError:
                if export.status == EXPORT_STATUS.SELECTED:
                    export.status = EXPORT_STATUS.UNSELECTED
                elif export.status == EXPORT_STATUS.TENTATIVE:
                    prune.add(export.tempId)
            else:
                if export.status == EXPORT_STATUS.UNSELECTED:
                    export.status = EXPORT_STATUS.SELECTED

        # delete tentative
        self.exports = [e for e in self.exports if e.tempId not in prune]

        # register all the rest (they're new)
        for face in selected.values():
            a = face.attributes.itemByName(_ATTR_GROUP, 'basename')
            if a:
                basename = a.value
                status = EXPORT_STATUS.SELECTED
            else:
                basename = face.body.name
                status = EXPORT_STATUS.TENTATIVE
            self.exports.append(FaceExport(
                face, face.tempId, basename, status))

        self._render_table()


def mk_export_dialog(app, cmd):
    # if app.activeEditObject.objectType != adsk.fusion.Sketch.classType():
    #     ui.messageBox('A sketch must be active for this command.')
    #     return False

    product = app.activeProduct
    design = adsk.fusion.Design.cast(product)
    if not design:
        raise Exception("No active Fusion design")

    cmd.okButtonText = "Export..."
    inputs = cmd.commandInputs

    select_id = 'select-exports'
    select = inputs.addSelectionInput(
        select_id, "Exports:", "Select faces to export")
    select.addSelectionFilter('PlanarFaces')
    select.setSelectionLimits(0, 0)

    exportsTable = ExportsTable(inputs, select_id)
    cmd.inputChanged.add(exportsTable)
    handlers.append(exportsTable)

    bodies = design.rootComponent.bRepBodies
    for i in range(bodies.count):
        body = bodies.item(i)
        if body.attributes.itemByName(_ATTR_GROUP, 'export'):
            faces = body.faces
            for j in range(faces.count):
                face = faces.item(j)
                if face.attributes.itemByName(_ATTR_GROUP, 'basename'):
                    select.addSelection(face)

    return True


def run(context):
    global _app, _ui
    try:
        _app = adsk.core.Application.get()
        _ui = _app.userInterface

        cmdDefs = _ui.commandDefinitions

        btn = cmdDefs.itemById('gen-dxf-button')
        if btn:
            btn.deleteMe()

        btn = cmdDefs.addButtonDefinition('gen-dxf-button', "Generate DXF", "")

        h = ExportDialogHandler()
        btn.commandCreated.add(h)
        handlers.append(h)

        btn.execute()

        # panel = ui.allToolbarPanels.itemById('SolidScriptsAddinsPanel')
        # buttonControl = panel.controls.addCommand(btn)

        adsk.autoTerminate(False)

        # sel = ui.selectEntity("Select faces to export", "PlanarFaces")
        # ent = sel.entity
        # ui.messageBox(
        #     "%r: %r\n\ngroupNames: %r"
        #     % (type(ent),
        #        ent,
        #        ent.attributes.groupNames),
        #     "Entity info")

        # geom = ent.geometry
        # ui.messageBox("%r: %r" % (type(geom), geom), "Entity geometry info")

        # if isinstance(ent.geometry, core.Plane):
        #     ent.attributes.add("GenDXF", "filename", "foo-bar")

    except:
        if _ui:
            _ui.messageBox("Failed:\n%s" % (traceback.format_exc(),))


def stop(context):
    try:
        btn = _ui.commandDefinitions.itemById('gen-dxf-button')
        if btn:
            btn.deleteMe()

        panel = _ui.allToolbarPanels.itemById('SolidScriptsAddinsPanel')
        c = panel.controls.itemById('gen-dxf-button')
        if c:
            c.deleteMe()

    except:
        if _ui:
            _ui.messageBox("Failed:\n%s" % (traceback.format_exc(),))
