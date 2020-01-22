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

        """
        equilateral = inputs.addBoolValueInput(
            'equilateral', 'Equilateral', True, '', False)

        # Create the table, defining the number of columns and their relative widths.
        table = inputs.addTableCommandInput('sampleTable', 'Table', 2, '1:1')

        # Define some of the table properties.
        table.minimumVisibleRows = 3
        table.maximumVisibleRows = 6
        table.columnSpacing = 1
        table.rowSpacing = 1
        table.tablePresentationStyle = adsk.core.TablePresentationStyles.itemBorderTablePresentationStyle
        table.hasGrid = False

        # Create a button and add it to the toolbar of the table.
        button = inputs.addBoolValueInput('tbButton', 'Add Row', False)#, 'Resources/Add', False)
        table.addToolbarCommandInput(button)

        # Create a string value input and add it to the first row and column.
        stringInput = inputs.addStringValueInput('string1', '', 'Sample Text')
        stringInput.isReadOnly = True
        table.addCommandInput(stringInput, 0, 0, 0, 0)

        # Create a drop-down input and add it to the first row and second column.
        dropDown = inputs.addDropDownCommandInput('dropList1', '', adsk.core.DropDownStyles.TextListDropDownStyle)
        dropDown.listItems.add('Item 1', True, '')
        dropDown.listItems.add('Item 2', False, '')
        dropDown.listItems.add('Item 3', False, '')
        table.addCommandInput(dropDown, 0, 1, 0, 0)
        """

        table = inputs.addTableCommandInput(
            'output-file-list', "Output files", 3, "1:4:1")

        table.minimumVisibleRows = 3
        table.maximumVisibleRows = 8
        # table.columnSpacing = 1
        # table.rowSpacing = 1
        table.tablePresentationStyle = \
            adsk.core.TablePresentationStyles.itemBorderTablePresentationStyle
        # table.hasGrid = False

        # don't know why this has to be a _bool_ value input
        i = inputs.addBoolValueInput('add-file', "+ Add", False) # , "Resources/Add", False)
        table.addToolbarCommandInput(i)

        i = inputs.addStringValueInput('h1', "", "Enable")
        i.isReadOnly = True
        table.addCommandInput(i, 0, 0, 0, 0)
        i = inputs.addStringValueInput('h2', "", "Filename")
        i.isReadOnly = True
        table.addCommandInput(i, 0, 1, 0, 0)

        i = inputs.addBoolValueInput('include-1', "", True)
        i.value = True
        table.addCommandInput(i, 1, 0, 0, 0)
        i = inputs.addStringValueInput('filename-1', "", "left wall")
        table.addCommandInput(i, 1, 1, 0, 0)
        i = inputs.addBoolValueInput('del-1', "Delete", False)
        table.addCommandInput(i, 1, 2, 0, 0)

        exe = GenDXFExecuteHandler()
        cmd.execute.add(exe)
        handlers.append(exe)
        cancel = GenDXFCancelHandler()
        cmd.destroy.add(cancel)
        handlers.append(cancel)


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
