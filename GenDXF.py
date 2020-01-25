# ~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/Scripts/

# pro tip:
# sketch.isComputeDeferred = True

import os.path
import threading
import traceback

import adsk
from adsk import core, fusion


_ATTR_GROUP = "GenDXF"

_TABLE_ID = 'exports-table'

_CELL_ID = '%s-%d'

_app = None # type: core.Application

_ui = None # type: core.UserInterface

handlers = []


class FaceExport(object):
    TENTATIVE = 1
    SELECTED = 2
    UNSELECTED = 3

    def __init__(self, face_id, basename, status):
        self.face_id = face_id
        self.basename = basename
        self.status = status

    def get_status(self):
        return self._status

    def set_status(self, status):
        assert status in (self.TENTATIVE, self.SELECTED, self.UNSELECTED)
        self._status = status

    status = property(get_status, set_status)


class ExportDialogHandler(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        design = adsk.fusion.Design.cast(_app.activeProduct)
        if not design:
            raise Exception("No active Fusion design")
        root = design.rootComponent

        args = adsk.core.CommandCreatedEventArgs.cast(args)
        cmd = args.command

        prog = _ui.createProgressDialog()
        prog.isCancelButtonShown = True

        try:
            ok = mk_export_dialog(cmd, root, prog)
        except:
            _ui.messageBox("Error:\n%s" % (traceback.format_exc(),))
            ok = False

        if not ok:
            # causes a crash:
            # cmd.doExecute(True)
            adsk.terminate()
            return

        exe = ExecuteHandler(root)
        cmd.execute.add(exe)
        handlers.append(exe)

        cancel = CancelHandler()
        cmd.destroy.add(cancel)
        handlers.append(cancel)


def mk_export_dialog(cmd, root, prog):
    faces = scan_faces(root, prog)
    if prog.wasCancelled:
        return False

    cmd.okButtonText = "Export..."
    inputs = cmd.commandInputs

    select_id = 'select-exports'
    select = inputs.addSelectionInput(
        select_id, "Exports:", "Select faces to export")
    select.addSelectionFilter('PlanarFaces')
    select.setSelectionLimits(0, 0)

    table = ExportsTable(inputs, select_id)
    cmd.inputChanged.add(table)
    handlers.append(table)

    for face in faces:
        assert select.addSelection(face)

    table._update_selected(select)

    return True


def scan_faces(root, prog):
    bodies = root.bRepBodies

    export = []
    for i in range(bodies.count):
        body = bodies.item(i) # type: fusion.BRepBody
        if body.attributes.itemByName(_ATTR_GROUP, 'export'):
            export.append(body)
            # body.attributes.itemByName(_ATTR_GROUP, 'export').deleteMe()

    if not export:
        return []

    face_count = sum(body.faces.count for body in export)
    prog.show("Scanning faces...", "%v/%m (%p%) complete", 0, face_count, 1)

    prog_n, rs = 0, []
    for body in export:
        if prog.wasCancelled:
            break
        faces = body.faces
        for j in range(faces.count):
            if prog.wasCancelled:
                break
            face = faces.item(j)
            if face.attributes.itemByName(_ATTR_GROUP, 'basename'):
                # didn't work:
                # yield face
                rs.append(face)
                # face.attributes.itemByName(_ATTR_GROUP, 'basename').deleteMe()
            prog_n += 1
            prog.progressValue = prog_n

    prog.hide()
    return rs


def face_id(face):
    return "%s/%d" % (face.body.name, face.tempId)


def split_face_id(face_id):
    body_name, temp_id = face_id.rsplit("/", 1)
    return body_name, int(temp_id)


class ExportsTable(adsk.core.InputChangedEventHandler):
    def __init__(self, inputs, selectionInputId):
        super(ExportsTable, self).__init__()
        self.inputs = inputs # type: core.CommandInputs
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
        self.table.selectedRow = -1
        self.table.clear()

        # header row
        i = self.inputs.itemById('th1') \
            or self.inputs.addStringValueInput('h1', "", "Enable")
        i.isReadOnly = True
        assert self.table.addCommandInput(i, 0, 0, 0, 0)

        i = self.inputs.itemById('th2') \
            or self.inputs.addStringValueInput('h2', "", "Filename")
        i.isReadOnly = True
        assert self.table.addCommandInput(i, 0, 1, 0, 1)

        # the actual export file list
        seen_filenames = set()
        for row, export in enumerate(self.exports, start=1):
            cell = lambda field: _CELL_ID % (field, row)

            filename, n = export.basename, 1
            while filename in seen_filenames:
                n += 1
                filename = "%s (%d)" % (export.basename, n)
            seen_filenames.add(filename)

            # a couple hidden inputs
            for field, value in (('basename', export.basename),
                                 ('face-id', export.face_id)):
                _id = cell(field)
                i = self.inputs.itemById(_id)
                if i:
                    i.value = value
                else:
                    i = self.inputs.addStringValueInput(_id, "", value)
                    i.isReadOnly = True
                    i.isVisible = False

            _id = cell('include')
            i = self.inputs.itemById(_id)
            if not i:
                i = self.inputs.addBoolValueInput(_id, "", True)
                i.tooltip = "Whether to include the face in this export job"
            # signal execution to include also tentative in export ...
            i.value = export.status != FaceExport.UNSELECTED
            # ... but leave it out from the table
            if export.status != FaceExport.TENTATIVE:
                assert self.table.addCommandInput(i, row, 0, 0, 0)

            _id = cell('filename')
            i = self.inputs.itemById(_id)
            if i:
                i.value = filename
            else:
                i = self.inputs.addStringValueInput(_id, "", filename)
            assert self.table.addCommandInput(i, row, 1, 0, 0)

            _id = cell('ext')
            i = self.inputs.itemById(_id)
            if i:
                i.value = filename
            else:
                i = self.inputs.addStringValueInput(_id, "", ".dxf")
                i.isReadOnly = True
            assert self.table.addCommandInput(i, row, 2, 0, 0)

            _id = cell('remove')
            i = self.inputs.itemById(_id)
            if not i:
                i = self.inputs.addBoolValueInput(_id, "Remove", False)
                i.tooltip = "Remove the face from this list"
            assert self.table.addCommandInput(i, row, 3, 0, 0)

    def notify(self, args):
        try:
            self._notify(args)
        except:
            _ui.messageBox("Error:\n%s" % (traceback.format_exc(),))

    def _notify(self, args):
        args = adsk.core.InputChangedEventArgs.cast(args)

        if args.input.id == self.selectionInputId:
            select = args.input # type: core.SelectionCommandInput
            self._update_selected(select)

        elif "-" in args.input.id:
            field, row = args.input.id.rsplit("-", 1)
            if field == "remove":
                row = int(row)
                inputs = args.firingEvent.sender.commandInputs
                face_id = inputs.itemById(_CELL_ID % ('face-id', row)).value
                body_name, temp_id = split_face_id(face_id)
                self.exports = list(filter(
                    lambda e: e.face_id != face_id, self.exports))

                select = inputs.itemById(self.selectionInputId) # type: core.SelectionCommandInput
                selections = [
                    select.selection(i).entity
                    for i in range(select.selectionCount)
                ] # type: list[fusion.BRepFace]
                assert select.clearSelection()
                for face in selections:
                    if (face.body.name, face.tempId) != (body_name, temp_id):
                        assert select.addSelection(face)

                # self._render_table()
                # self._update_selected(select)

                """
                def defer():
                    import time
                    time.sleep(5)
                    self._render_table()

                t = threading.Thread(target=defer)
                t.start()
                """

    def _update_selected(self, select):
        selected = {}
        for i in range(select.selectionCount):
            face = select.selection(i).entity # type: fusion.BRepFace
            selected[face_id(face)] = face

        prune = set()
        for export in self.exports:
            try:
                selected.pop(export.face_id)
            except KeyError:
                if export.status == FaceExport.SELECTED:
                    export.status = FaceExport.UNSELECTED
                elif export.status == FaceExport.TENTATIVE:
                    prune.add(export.face_id)
            else:
                if export.status == FaceExport.UNSELECTED:
                    export.status = FaceExport.SELECTED

        # delete tentative
        self.exports = list(filter(
            lambda e: e.face_id not in prune, self.exports))

        # register all the rest (they're new)
        for face in selected.values():
            a = face.attributes.itemByName(_ATTR_GROUP, 'basename')
            if a:
                basename = a.value
                status = FaceExport.SELECTED
            else:
                basename = face.body.name.replace(os.path.sep, "_")
                status = FaceExport.TENTATIVE
            self.exports.append(FaceExport(face_id(face), basename, status))

        self._render_table()


class ExecuteHandler(adsk.core.CommandEventHandler):
    def __init__(self, root):
        super(ExecuteHandler, self).__init__()
        self.root = root # type: fusion.Component

    def notify(self, args):
        try:
            self._notify(args)
        except:
            _ui.messageBox("Error:\n%s" % (traceback.format_exc(),))

    def _notify(self, args):
        args = adsk.core.CommandEventArgs.cast(args)
        inputs = args.command.commandInputs
        table = inputs.itemById(_TABLE_ID)

        if any(inputs.itemById(_CELL_ID % ('include', row)).value
               for row in range(1, table.rowCount)):
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

        else:
            dir = None

        _bodies = self.root.bRepBodies
        bodies = {}
        for i in range(_bodies.count):
            body = _bodies.item(i)
            bodies[body.name] = body

        for row in range(1, table.rowCount):
            def input(field):
                return inputs.itemById(_CELL_ID % (field, row)).value

            face_id, basename = map(input, ('face-id', 'basename'))
            body_name, temp_id = split_face_id(face_id)
            body = bodies[body_name]
            faces = body.findByTempId(temp_id)
            assert len(faces) == 1, "face tempId collision"
            face = faces[0]

            # export first, to inhibit permanent export flag on failure
            if input('include'):
                filename = input('filename') + input('ext')
                _ui.messageBox("Generating %s%s%s" % (dir, os.path.sep, filename))
                # sketches = rootComp.sketches
                # sketch = sketches.add()

            face.attributes.add(_ATTR_GROUP, 'basename', basename)
            body.attributes.add(_ATTR_GROUP, 'export', "yes")

        adsk.terminate()


class CancelHandler(adsk.core.CommandEventHandler):
    def notify(self, args):
        adsk.terminate()


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
