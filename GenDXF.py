# ~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/Scripts/

# pro tip:
# sketch.isComputeDeferred = True

import traceback

import adsk
from adsk import core, fusion


handlers = []


class GenDXFExecuteHandler(adsk.core.CommandEventHandler):
    def notify(self, args):
        args = adsk.core.CommandEventArgs.cast(args)
        inputs = args.command.commandInputs

        app = adsk.core.Application.get()
        ui = app.userInterface

        if inputs.itemById('equilateral').value is True:
            ui.messageBox("equilateral")
        else:
            ui.messageBox("not equilateral")

        adsk.terminate()


class GenDXFCancelHandler(adsk.core.CommandEventHandler):
    def notify(self, args):
        adsk.terminate()


class GenDXFEventHandler(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        app = adsk.core.Application.get()
        try:
            cmd = mkExportDialog(app)
        except:
            app.userInterface.messageBox("Error:\n%s" % (traceback.format_exc(),))
            adsk.terminate()
            return False

        if not cmd:
            adsk.terminate()
            return False

        exe = GenDXFExecuteHandler()
        cmd.execute.add(exe)
        handlers.append(exe)

        cancel = GenDXFCancelHandler()
        cmd.destroy.add(cancel)
        handlers.append(cancel)


def mkExportDialog(app):
    # if app.activeEditObject.objectType != adsk.fusion.Sketch.classType():
    #     ui.messageBox('A sketch must be active for this command.')
    #     return False

    product = app.activeProduct
    design = adsk.fusion.Design.cast(product)
    if not design:
        raise Exception("No active Fusion design")

    root = design.rootComponent
    bodies = root.bRepBodies
    names = []
    for i in range(bodies.count):
        body = bodies.item(i)
        faces = body.faces
        names.append((i, "%s (%d)" % (body.name, faces.count)))
        for j in range(faces.count):
            face = faces.item(j)

        # try:
        #     x = xs.item(i)
        # except:
        #     continue
        # else:
        #     if x:
        #         names.append((i, x.objectType))

        # try:
        #     x = xs.item(i)
        #     names += "\n%s" % x.objectType
        # except Exception as e:
        #     names += "\n%s" % e
        #     break
        # names += "\n%s (%d)" % (x.name, x.faces.count)
        # names += "\n%s" % x.name

    msg = "%d features:\n%s" % (len(names), "\n".join("%d: %s" % i for i in names))
    app.userInterface.messageBox(msg, "Feats")
    adsk.terminate()
    return False

    args = adsk.core.CommandCreatedEventArgs.cast(args)
    cmd = args.command
    cmd.okButtonText = "Export"
    inputs = cmd.commandInputs

    table = inputs.addTableCommandInput(
        'output-file-list', "Output files", 4, "1:3:1:1")

    table.minimumVisibleRows = 3
    table.maximumVisibleRows = 8
    table.tablePresentationStyle = \
        adsk.core.TablePresentationStyles.itemBorderTablePresentationStyle

    i = inputs.addBoolValueInput('add-file', "+ Add", False) # , "Resources/Add", False)
    table.addToolbarCommandInput(i)

    i = inputs.addStringValueInput('h1', "", "Enable")
    i.isReadOnly = True
    table.addCommandInput(i, 0, 0, 0, 0)
    i = inputs.addStringValueInput('h2', "", "Filename")
    i.isReadOnly = True
    table.addCommandInput(i, 0, 1, 0, 1)

    i = inputs.addBoolValueInput('include-1', "", True)
    i.value = True
    table.addCommandInput(i, 1, 0, 0, 0)
    i = inputs.addStringValueInput('filename-1', "", "left wall")
    table.addCommandInput(i, 1, 1, 0, 0)
    i = inputs.addStringValueInput('ext-1', "", ".dxf")
    i.isReadOnly = True
    table.addCommandInput(i, 1, 2, 0, 0)
    i = inputs.addBoolValueInput('del-1', "Delete", False)
    table.addCommandInput(i, 1, 3, 0, 0)

    return cmd


def run(context):
    ui = None
    try:
        app = core.Application.get()
        ui = app.userInterface

        # design = fusion.Design(app.activeProduct)
        # root = design.rootComponent.occurrences

        cmdDefs = ui.commandDefinitions

        btn = ui.commandDefinitions.itemById('gen-dxf-button')
        if btn:
            btn.deleteMe()

        btn = cmdDefs.addButtonDefinition(
            'gen-dxf-button', # ID
            "Generate DXF", # name
            "", # tooltip
            # resourceFolder='./Resources/Sample',
        )

        h = GenDXFEventHandler()
        btn.commandCreated.add(h)
        handlers.append(h)

        btn.execute()

        # panel = ui.allToolbarPanels.itemById('SolidScriptsAddinsPanel')
        # buttonControl = panel.controls.addCommand(btn)

        # Keep the script running.
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
        if ui:
            ui.messageBox("Failed:\n%s" % (traceback.format_exc(),))


def stop(context):
    ui = None
    try:
        app = adsk.core.Application.get()
        ui  = app.userInterface

        # Clean up the UI.
        btn = ui.commandDefinitions.itemById('gen-dxf-button')
        if btn:
            btn.deleteMe()

        panel = ui.allToolbarPanels.itemById('SolidScriptsAddinsPanel')
        c = panel.controls.itemById('gen-dxf-button')
        if c:
            c.deleteMe()

    except:
        if ui:
            ui.messageBox("Failed:\n%s" % (traceback.format_exc(),))
