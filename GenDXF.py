import traceback

import adsk
from adsk import core, fusion


handlers = []


# pro tip:
# sketch.isComputeDeferred = True

#
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


class GexDXFEventHandler(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        # app = adsk.core.Application.get()
        # if app.activeEditObject.objectType != adsk.fusion.Sketch.classType():
        #     ui = app.userInterface
        #     ui.messageBox('A sketch must be active for this command.')
        #     return False

        args = adsk.core.CommandCreatedEventArgs.cast(args)
        cmd = args.command
        inputs = cmd.commandInputs

        equilateral = inputs.addBoolValueInput(
            'equilateral', 'Equilateral', True, '', False)

        exe = GenDXFExecuteHandler()
        cmd.execute.add(exe)
        handlers.append(exe)


def run(context):
    ui = None
    try:
        app = core.Application.get()
        ui = app.userInterface

        # design = fusion.Design(app.activeProduct)
        # root = design.rootComponent.occurrences

        cmdDefs = ui.commandDefinitions

        btn = cmdDefs.addButtonDefinition(
            'gen-dxf-button', # ID
            "Generate DXF", # name
            "", # tooltip
            # resourceFolder='./Resources/Sample',
        )

        h = GexDXFEventHandler()
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
