# ~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/Scripts/

# pro tip:
# sketch.isComputeDeferred = True

from collections import namedtuple
import os.path
import re
import threading
import traceback

import adsk
from adsk import core, fusion


_ATTR_GROUP = "GenDXF"

_TABLE_ID = 'exports-table'

_app = None # type: core.Application
_ui = None # type: core.UserInterface
handlers = []
_scan_cache = [] # type: list[fusion.BRepFace]

COL = namedtuple(
    "ColumnOrder",
    ('FACE_ID', 'INCLUDE', 'FILENAME', 'EXT', 'REMOVE')) \
    (0, 1, 2, 3, 4)

# characters that aren't allowed in input IDs
_non_id = re.compile(r"[^a-zA-Z0-9\-]")


class FaceExport(object):
    TENTATIVE = 1
    SELECTED = 2
    UNSELECTED = 3

    def __init__(self, face_id, filename, status):
        self.face_id = face_id
        self.filename = filename
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
            _ui.messageBox("Error:\n%s" % (traceback.format_exc(),), "Error")
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
    global _scan_cache

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
            if face.attributes.itemByName(_ATTR_GROUP, 'filename'):
                # didn't work:
                # yield face
                rs.append(face)
                # face.attributes.itemByName(_ATTR_GROUP, 'filename').deleteMe()
            prog_n += 1
            prog.progressValue = prog_n

    prog.hide()
    _scan_cache = rs
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
        _render_table(self.inputs, self.exports)

    def _mk_table(self):
        table = self.inputs.addTableCommandInput(
            _TABLE_ID, "Output files", 4, "0:1:3:1:1")
        table.minimumVisibleRows = 3
        table.maximumVisibleRows = 8
        table.tablePresentationStyle = \
            adsk.core.TablePresentationStyles.itemBorderTablePresentationStyle
        return table

    def notify(self, args):
        try:
            self._notify(args)
        except:
            _ui.messageBox("Error:\n%s" % (traceback.format_exc(),), "Error")

    def _notify(self, args):
        args = adsk.core.InputChangedEventArgs.cast(args)

        if args.input.id == self.selectionInputId:
            select = args.input # type: core.SelectionCommandInput
            self._update_selected(select)
            return

        inputs = args.firingEvent.sender.commandInputs
        table = inputs.itemById(_TABLE_ID) # type: core.TableCommandInput
        found, row, col, r_span, c_span = table.getPosition(args.input)
        if found:
            if col == COL.REMOVE:
                face_id = table.getInputAtPosition(row, COL.FACE_ID).value
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
                t = threading.Thread(target=del_row, args=[inputs, face_id])
                t.start()
                return

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
            a = face.attributes.itemByName(_ATTR_GROUP, 'filename')
            if a:
                filename = a.value
                status = FaceExport.SELECTED
            else:
                basename = face.body.name.replace(os.path.sep, "_")
                filename, n = basename, 1
                while any(filename == e.filename for e in self.exports):
                    n += 1
                    filename = "%s (%d)" % (basename, n)
                status = FaceExport.TENTATIVE
            self.exports.append(FaceExport(face_id(face), filename, status))

        _render_table(self.inputs, self.exports)


def _render_table(inputs, exports):
    table = inputs.itemById(_TABLE_ID) # type: core.TableCommandInput
    table.clear()

    # header row
    i = inputs.itemById('th1') \
        or inputs.addStringValueInput('th1', "", "Include")
    i.isReadOnly = True
    assert table.addCommandInput(i, 0, COL.INCLUDE, 0, 0)

    i = inputs.itemById('th2') \
        or inputs.addStringValueInput('th2', "", "Filename")
    i.isReadOnly = True
    assert table.addCommandInput(i, 0, COL.FILENAME, 0, 1)

    # the actual export file list
    for row, export in enumerate(exports, start=1):
        def mk_id(field):
            # spaces are allowed, per se, but keepin' it real
            return _non_id.sub("_", "%s-%s" % (field, export.face_id)) \
                          .replace(" ", "-")

        # a hidden input
        id = mk_id('face-id')
        i = inputs.itemById(id)
        if i:
            # _just_ in case...
            i.value = export.face_id
        else:
            i = inputs.addStringValueInput(id, "", export.face_id)
            i.isReadOnly = True
            i.isVisible = False
        assert table.addCommandInput(i, row, COL.FACE_ID, 0, 0)

        id = mk_id('include')
        i = inputs.itemById(id)
        if not i:
            i = inputs.addBoolValueInput(id, "", True)
            i.tooltip = "Whether to include the face in this export job"
        # tentatives are always included
        i.value = export.status != FaceExport.UNSELECTED
        if export.status == FaceExport.TENTATIVE:
            i.isVisible = False
        else:
            i.isVisible = True
        assert table.addCommandInput(i, row, COL.INCLUDE, 0, 0)

        id = mk_id('filename')
        i = inputs.itemById(id)
        if i:
            i.value = export.filename
        else:
            i = inputs.addStringValueInput(id, "", export.filename)
        assert table.addCommandInput(i, row, COL.FILENAME, 0, 0)

        id = mk_id('ext')
        i = inputs.itemById(id)
        if not i:
            i = inputs.addStringValueInput(id, "", ".dxf")
            i.isReadOnly = True
        assert table.addCommandInput(i, row, COL.EXT, 0, 0)

        id = mk_id('remove')
        i = inputs.itemById(id)
        if not i:
            i = inputs.addBoolValueInput(id, "Remove", False)
            i.tooltip = "Remove the face from this list"
        assert table.addCommandInput(i, row, COL.REMOVE, 0, 0)


def del_row(inputs, face_id):
    import time
    time.sleep(.1)
    table = inputs.itemById(_TABLE_ID) # type: core.TableCommandInput
    for row in range(1, table.rowCount):
        if table.getInputAtPosition(row, COL.FACE_ID).value == face_id:
            table.deleteRow(row)
            break


class ExecuteHandler(adsk.core.CommandEventHandler):
    def __init__(self, root):
        super(ExecuteHandler, self).__init__()
        self.root = root # type: fusion.Component

    def notify(self, args):
        try:
            self._notify(args)
        except:
            _ui.messageBox("Error:\n%s" % (traceback.format_exc(),), "Error")

    def _notify(self, args):
        args = adsk.core.CommandEventArgs.cast(args)
        inputs = args.command.commandInputs
        table = inputs.itemById(_TABLE_ID) # type: core.TableCommandInput

        if any(table.getInputAtPosition(row, COL.INCLUDE).valu
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

        keep = set()

        for row in range(1, table.rowCount):
            face_id = table.getInputAtPosition(row, COL.FACE_ID).value
            body_name, temp_id = split_face_id(face_id)
            keep.add((body_name, temp_id))
            body = bodies[body_name]
            faces = body.findByTempId(temp_id)
            assert len(faces) == 1, "face tempId collision"
            face = faces[0]
            filename = table.getInputAtPosition(row, COL.FILENAME).value
            # export first, to inhibit permanent export flag on failure
            if table.getInputAtPosition(row, COL.INCLUDE).value:
                out = filename + table.getInputAtPosition(row, COL.EXT).value
                _ui.messageBox("Generating %s%s%s" % (dir, os.path.sep, out))
                # sketches = rootComp.sketches
                # sketch = sketches.add()

            face.attributes.add(_ATTR_GROUP, 'filename', filename)
            body.attributes.add(_ATTR_GROUP, 'export', "yes")

        for face in _scan_cache:
            if (face.body.name, face.tempId) not in keep:
                a = face.attributes.itemByName(_ATTR_GROUP, 'filename')
                if a:
                    a.deleteMe()

            body = face.body
            if not any(body.faces.item(j).attributes.itemByName(_ATTR_GROUP, 'filename')
                       for j in range(body.faces.count)):
                a = body.attributes.itemByName(_ATTR_GROUP, 'export')
                if a:
                    a.deleteMe()

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

    except:
        if _ui:
            _ui.messageBox("Failed:\n%s" % (traceback.format_exc(),), "Error")


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
            _ui.messageBox("Failed:\n%s" % (traceback.format_exc(),), "Error")
