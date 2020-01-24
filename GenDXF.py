# ~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/Scripts/

# pro tip:
# sketch.isComputeDeferred = True

from collections import OrderedDict, namedtuple
import traceback

import adsk
from adsk import core, fusion


ATTR_GROUP = "GenDXF"

_app = _ui = None

handlers = []

FaceExport = namedtuple('FaceExport', ('face', 'tempId', 'basename', 'status'))

EXPORT_STATUS = namedtuple(
    'ExportStatus',
    ('TENTATIVE', 'SELECTED', 'UNSELECTED')) \
    (1, 2, 3)


class GenDXFExecuteHandler(adsk.core.CommandEventHandler):
    def notify(self, args):
        args = adsk.core.CommandEventArgs.cast(args)
        inputs = args.command.commandInputs

        # sketches = rootComp.sketches
        # sketch = sketches.add()

        if inputs.itemById('equilateral').value is True:
            _ui.messageBox("equilateral")
        else:
            _ui.messageBox("not equilateral")

        adsk.terminate()


class GenDXFCancelHandler(adsk.core.CommandEventHandler):
    def notify(self, args):
        adsk.terminate()


class GenDXFEventHandler(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        app = adsk.core.Application.get()
        args = adsk.core.CommandCreatedEventArgs.cast(args)
        cmd = args.command

        try:
            ok = mkExportDialog(app, cmd)
        except:
            app.userInterface.messageBox("Error:\n%s" % (traceback.format_exc(),))
            adsk.terminate()
            return False

        if not ok:
            adsk.terminate()
            return False

        exe = GenDXFExecuteHandler()
        cmd.execute.add(exe)
        handlers.append(exe)

        cancel = GenDXFCancelHandler()
        cmd.destroy.add(cancel)
        handlers.append(cancel)


class ExportsTable(adsk.core.InputChangedEventHandler):
    def __init__(self, inputs, tableId, selectionInputId):
        super(ExportsTable, self).__init__()
        self.inputs = inputs
        self.selectionInputId = selectionInputId
        self.exports = [] # type: list[FaceExport]
        self.table = self._mk_table(tableId) # type: core.TableCommandInput
        self._render_table()

    def _mk_table(self, tableId):
        table = self.inputs.addTableCommandInput(
            tableId, "Output files", 4, "1:3:1:1")
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

            # TODO include tempId

            i = self.inputs.addBoolValueInput('include-%d' % row, "", True)
            i.value = True
            assert self.table.addCommandInput(i, row, 0, 0, 0)
            i = self.inputs.addStringValueInput('filename-%d' % row, "", filename)
            assert self.table.addCommandInput(i, row, 1, 0, 0)
            i = self.inputs.addStringValueInput('ext-%d' % row, "", ".dxf")
            i.isReadOnly = True
            assert self.table.addCommandInput(i, row, 2, 0, 0)
            i = self.inputs.addBoolValueInput('del-%d' % row, "Delete", False)
            assert self.table.addCommandInput(i, row, 3, 0, 0)

    def notify(self, args):
        args = adsk.core.InputChangedEventArgs.cast(args)
        if args.input.id == self.selectionInputId:
            select = args.input # type: core.SelectionCommandInput

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

            # delete tentative
            self.exports = [e for e in self.exports if e.tempId not in prune]

            # register all the rest (they're new)
            for face in selected.values():
                # these weren't in exports, must be tentative
                assert not face.attributes.itemByName(ATTR_GROUP, 'basename')
                self.exports.append(FaceExport(
                    face, face.tempId, face.body.name, EXPORT_STATUS.TENTATIVE))

            self._render_table()

            # sample code:
            # inputs = args.firingEvent.sender.commandInputs
            # scaleInput = inputs.itemById('heightScale')


def mkExportDialog(app, cmd):
    # if app.activeEditObject.objectType != adsk.fusion.Sketch.classType():
    #     ui.messageBox('A sketch must be active for this command.')
    #     return False

    product = app.activeProduct
    design = adsk.fusion.Design.cast(product)
    if not design:
        raise Exception("No active Fusion design")

    cmd.okButtonText = "Export"
    inputs = cmd.commandInputs

    select = inputs.addSelectionInput(
        'select-exports', "Exports:", "Select faces to export")
    select.addSelectionFilter('PlanarFaces')
    select.setSelectionLimits(0, 0)

    exportsTable = ExportsTable(inputs, 'export-list', 'select-exports')
    cmd.inputChanged.add(exportsTable)
    handlers.append(exportsTable)

    bodies = design.rootComponent.bRepBodies
    for i in range(bodies.count):
        body = bodies.item(i)
        if body.attributes.itemByName(ATTR_GROUP, 'export'):
            faces = body.faces
            for j in range(faces.count):
                face = faces.item(j)
                if face.attributes.itemByName(ATTR_GROUP, 'basename'):
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

        h = GenDXFEventHandler()
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
