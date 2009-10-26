#!/usr/bin/python

"""
@todo Add preference file
	@li enable/disable plugins
	@li plugin search path
	@li Number format
	@li Current tab
@todo Expand operations to support
	@li mathml then to cairo?
	@li cairo directly?
@todo Expanded copy/paste (Unusure how far to go)
	@li Copy formula, value, serialized, mathml, latex?
	@li Paste serialized, value?

Some useful things on Maemo
@li http://maemo.org/api_refs/4.1/libosso-2.16-1/group__Statesave.html
@li http://maemo.org/api_refs/4.1/libosso-2.16-1/group__Autosave.html
"""


from __future__ import with_statement


import sys
import gc
import os
import string
import logging
import warnings

import gtk
import gtk.glade

import hildonize

from libraries import gtkpie
from libraries import gtkpieboard
import plugin_utils
import history
import gtkhistory
import gtk_toolbox
import constants


_moduleLogger = logging.getLogger("ejpi_glade")

PLUGIN_SEARCH_PATHS = [
	os.path.join(os.path.dirname(__file__), "plugins/"),
]


class ValueEntry(object):

	def __init__(self, widget):
		self.__widget = widget
		self.__actualEntryDisplay = ""

	def get_value(self):
		value = self.__actualEntryDisplay.strip()
		if any(
			0 < value.find(whitespace)
			for whitespace in string.whitespace
		):
			self.clear()
			raise ValueError('Invalid input "%s"' % value)
		return value

	def set_value(self, value):
		value = value.strip()
		if any(
			0 < value.find(whitespace)
			for whitespace in string.whitespace
		):
			raise ValueError('Invalid input "%s"' % value)
		self.__actualEntryDisplay = value
		self.__widget.set_text(value)

	def append(self, value):
		value = value.strip()
		if any(
			0 < value.find(whitespace)
			for whitespace in string.whitespace
		):
			raise ValueError('Invalid input "%s"' % value)
		self.set_value(self.get_value() + value)

	def pop(self):
		value = self.get_value()[0:-1]
		self.set_value(value)

	def clear(self):
		self.set_value("")

	value = property(get_value, set_value, clear)


class Calculator(object):

	_glade_files = [
		'/usr/lib/ejpi/ejpi.glade',
		os.path.join(os.path.dirname(__file__), "ejpi.glade"),
		os.path.join(os.path.dirname(__file__), "../lib/ejpi.glade"),
	]

	_plugin_search_paths = [
		"/usr/lib/ejpi/plugins/",
		os.path.join(os.path.dirname(__file__), "plugins/"),
	]

	_user_data = os.path.expanduser("~/.%s/" % constants.__app_name__)
	_user_settings = "%s/settings.ini" % _user_data
	_user_history = "%s/history.stack" % _user_data

	def __init__(self):
		self.__constantPlugins = plugin_utils.ConstantPluginManager()
		self.__constantPlugins.add_path(*self._plugin_search_paths)
		for pluginName in ["Builtin", "Trigonometry", "Computer", "Alphabet"]:
			try:
				pluginId = self.__constantPlugins.lookup_plugin(pluginName)
				self.__constantPlugins.enable_plugin(pluginId)
			except:
				warnings.warn("Failed to load plugin %s" % pluginName)

		self.__operatorPlugins = plugin_utils.OperatorPluginManager()
		self.__operatorPlugins.add_path(*self._plugin_search_paths)
		for pluginName in ["Builtin", "Trigonometry", "Computer", "Alphabet"]:
			try:
				pluginId = self.__operatorPlugins.lookup_plugin(pluginName)
				self.__operatorPlugins.enable_plugin(pluginId)
			except:
				warnings.warn("Failed to load plugin %s" % pluginName)

		self.__keyboardPlugins = plugin_utils.KeyboardPluginManager()
		self.__keyboardPlugins.add_path(*self._plugin_search_paths)
		self.__activeKeyboards = []

		for path in self._glade_files:
			if os.path.isfile(path):
				self._widgetTree = gtk.glade.XML(path)
				break
		else:
			self.display_error_message("Cannot find ejpi.glade")
			gtk.main_quit()
			return
		try:
			os.makedirs(self._user_data)
		except OSError, e:
			if e.errno != 17:
				raise

		self._clipboard = gtk.clipboard_get()
		self._window = self._widgetTree.get_widget("mainWindow")

		self._app = None
		self._isFullScreen = False
		self._app = hildonize.get_app_class()()
		self._window = hildonize.hildonize_window(self._app, self._window)

		menu = hildonize.hildonize_menu(
			self._window,
			self._widgetTree.get_widget("mainMenubar"),
			[]
		)

		for scrollingWidgetName in (
			"scrollingHistory",
		):
			scrollingWidget = self._widgetTree.get_widget(scrollingWidgetName)
			assert scrollingWidget is not None, scrollingWidgetName
			hildonize.hildonize_scrollwindow_with_viewport(scrollingWidget)

		self.__errorDisplay = gtk_toolbox.ErrorDisplay(self._widgetTree)
		self.__userEntry = ValueEntry(self._widgetTree.get_widget("entryView"))
		self.__stackView = self._widgetTree.get_widget("historyView")
		self.__pluginButton = self._widgetTree.get_widget("keyboardSelectionButton")

		self.__historyStore = gtkhistory.GtkCalcHistory(self.__stackView)
		self.__history = history.RpnCalcHistory(
			self.__historyStore,
			self.__userEntry, self.__errorDisplay,
			self.__constantPlugins.constants, self.__operatorPlugins.operators
		)
		self.__load_history()

		self.__sliceStyle = gtkpie.generate_pie_style(gtk.Button())
		self.__handler = gtkpieboard.KeyboardHandler(self._on_entry_direct)
		self.__handler.register_command_handler("push", self._on_push)
		self.__handler.register_command_handler("unpush", self._on_unpush)
		self.__handler.register_command_handler("backspace", self._on_entry_backspace)
		self.__handler.register_command_handler("clear", self._on_entry_clear)

		builtinKeyboardId = self.__keyboardPlugins.lookup_plugin("Builtin")
		self.__keyboardPlugins.enable_plugin(builtinKeyboardId)
		self.__builtinPlugin = self.__keyboardPlugins.keyboards["Builtin"].construct_keyboard()
		self.__builtinKeyboard = self.__builtinPlugin.setup(self.__history, self.__sliceStyle, self.__handler)
		self._widgetTree.get_widget("mainKeyboard").pack_start(self.__builtinKeyboard)
		self.enable_plugin(self.__keyboardPlugins.lookup_plugin("Trigonometry"))
		self.enable_plugin(self.__keyboardPlugins.lookup_plugin("Computer"))
		self.enable_plugin(self.__keyboardPlugins.lookup_plugin("Alphabet"))

		callbackMapping = {
			"on_calculator_quit": self._on_close,
			"on_paste": self._on_paste,
			"on_clear_history": self._on_clear_all,
			"on_about": self._on_about_activate,
		}
		self._widgetTree.signal_autoconnect(callbackMapping)
		self._widgetTree.get_widget("copyMenuItem").connect("activate", self._on_copy)
		self._widgetTree.get_widget("copyEquationMenuItem").connect("activate", self._on_copy_equation)
		self._window.connect("key-press-event", self._on_key_press)
		self._window.connect("window-state-event", self._on_window_state_change)
		self._widgetTree.get_widget("entryView").connect("activate", self._on_push)
		self.__pluginButton.connect("clicked", self._on_kb_plugin_selection_button)

		self._set_plugin_kb(0)

		hildonize.set_application_title(self._window, "%s" % constants.__pretty_app_name__)
		self._window.connect("destroy", self._on_close)
		self._window.show_all()

		if not hildonize.IS_HILDON_SUPPORTED:
			_moduleLogger.warning("No hildonization support")

		try:
			import osso
		except ImportError:
			osso = None
		self._osso = None
		if osso is not None:
			self._osso = osso.Context(constants.__app_name__, constants.__version__, False)
			device = osso.DeviceState(self._osso)
			device.set_device_state_callback(self._on_device_state_change, 0)
		else:
			_moduleLogger.warning("No OSSO support")

	def display_error_message(self, msg):
		error_dialog = gtk.MessageDialog(None, 0, gtk.MESSAGE_ERROR, gtk.BUTTONS_CLOSE, msg)

		def close(dialog, response, editor):
			editor.about_dialog = None
			dialog.destroy()
		error_dialog.connect("response", close, self)
		error_dialog.run()

	def enable_plugin(self, pluginId):
		self.__keyboardPlugins.enable_plugin(pluginId)
		pluginData = self.__keyboardPlugins.plugin_info(pluginId)
		pluginName = pluginData[0]
		plugin = self.__keyboardPlugins.keyboards[pluginName].construct_keyboard()
		pluginKeyboard = plugin.setup(self.__history, self.__sliceStyle, self.__handler)

		self.__activeKeyboards.append({
			"pluginName": pluginName,
			"plugin": plugin,
			"pluginKeyboard": pluginKeyboard,
		})

	def _on_kb_plugin_selection_button(self, *args):
		pluginNames = [plugin["pluginName"] for plugin in self.__activeKeyboards]
		oldIndex = pluginNames.index(self.__pluginButton.get_label())
		newIndex = hildonize.touch_selector(self._window, "Keyboards", pluginNames, oldIndex)
		self._set_plugin_kb(newIndex)

	def _set_plugin_kb(self, pluginIndex):
		plugin = self.__activeKeyboards[pluginIndex]
		self.__pluginButton.set_label(plugin["pluginName"])
		pluginParent = self._widgetTree.get_widget("pluginKeyboard")
		oldPluginChildren = pluginParent.get_children()
		if oldPluginChildren:
			assert len(oldPluginChildren) == 1, "%r" % (oldPluginChildren, )
			pluginParent.remove(oldPluginChildren[0])
			oldPluginChildren[0].hide()
		pluginKeyboard = plugin["pluginKeyboard"]
		pluginParent.pack_start(pluginKeyboard)
		pluginKeyboard.show_all()

	def __load_history(self):
		serialized = []
		try:
			with open(self._user_history, "rU") as f:
				serialized = (
					(part.strip() for part in line.split(" "))
					for line in f.readlines()
				)
		except IOError, e:
			if e.errno != 2:
				raise
		self.__history.deserialize_stack(serialized)

	def __save_history(self):
		serialized = self.__history.serialize_stack()
		with open(self._user_history, "w") as f:
			for lineData in serialized:
				line = " ".join(data for data in lineData)
				f.write("%s\n" % line)

	def _on_device_state_change(self, shutdown, save_unsaved_data, memory_low, system_inactivity, message, userData):
		"""
		For system_inactivity, we have no background tasks to pause

		@note Hildon specific
		"""
		if memory_low:
			gc.collect()

		if save_unsaved_data or shutdown:
			self.__save_history()

	def _on_window_state_change(self, widget, event, *args):
		"""
		@note Hildon specific
		"""
		if event.new_window_state & gtk.gdk.WINDOW_STATE_FULLSCREEN:
			self._isFullScreen = True
		else:
			self._isFullScreen = False

	def _on_close(self, *args, **kwds):
		if self._osso is not None:
			self._osso.close()

		try:
			self.__save_history()
		finally:
			gtk.main_quit()

	def _on_copy(self, *args):
		try:
			equationNode = self.__history.history.peek()
			result = str(equationNode.evaluate())
			self._clipboard.set_text(result)
		except StandardError, e:
			self.__errorDisplay.push_exception()

	def _on_copy_equation(self, *args):
		try:
			equationNode = self.__history.history.peek()
			equation = str(equationNode)
			self._clipboard.set_text(equation)
		except StandardError, e:
			self.__errorDisplay.push_exception()

	def _on_paste(self, *args):
		contents = self._clipboard.wait_for_text()
		self.__userEntry.append(contents)

	def _on_key_press(self, widget, event, *args):
		"""
		@note Hildon specific
		"""
		RETURN_TYPES = (gtk.keysyms.Return, gtk.keysyms.ISO_Enter, gtk.keysyms.KP_Enter)
		if (
			event.keyval == gtk.keysyms.F6 or
			event.keyval in RETURN_TYPES and event.get_state() & gtk.gdk.CONTROL_MASK
		):
			if self._isFullScreen:
				self._window.unfullscreen()
			else:
				self._window.fullscreen()

	def _on_push(self, *args):
		self.__history.push_entry()

	def _on_unpush(self, *args):
		self.__historyStore.unpush()

	def _on_entry_direct(self, keys, modifiers):
		if "shift" in modifiers:
			keys = keys.upper()
		self.__userEntry.append(keys)

	def _on_entry_backspace(self, *args):
		self.__userEntry.pop()

	def _on_entry_clear(self, *args):
		self.__userEntry.clear()

	def _on_clear_all(self, *args):
		self.__history.clear()

	def _on_about_activate(self, *args):
		dlg = gtk.AboutDialog()
		dlg.set_name(constants.__pretty_app_name__)
		dlg.set_version(constants.__version__)
		dlg.set_copyright("Copyright 2008 - LGPL")
		dlg.set_comments("""
ejpi A Touch Screen Optimized RPN Calculator for Maemo and Linux.

RPN: Stack based math, its fun
Buttons: Try both pressing and hold/drag
History: Try dragging things around, deleting them, etc
""")
		dlg.set_website("http://ejpi.garage.maemo.org")
		dlg.set_authors(["Ed Page"])
		dlg.run()
		dlg.destroy()


def run_doctest():
	import doctest

	failureCount, testCount = doctest.testmod()
	if not failureCount:
		print "Tests Successful"
		sys.exit(0)
	else:
		sys.exit(1)


def run_calculator():
	gtk.gdk.threads_init()

	gtkpie.IMAGES.add_path(os.path.join(os.path.dirname(__file__), "libraries/images"), )
	handle = Calculator()
	gtk.main()


class DummyOptions(object):

	def __init__(self):
		self.test = False


if __name__ == "__main__":
	logging.basicConfig(level=logging.DEBUG)
	if len(sys.argv) > 1:
		try:
			import optparse
		except ImportError:
			optparse = None

		if optparse is not None:
			parser = optparse.OptionParser()
			parser.add_option("-t", "--test", action="store_true", dest="test", help="Run tests")
			(commandOptions, commandArgs) = parser.parse_args()
	else:
		commandOptions = DummyOptions()
		commandArgs = []

	if commandOptions.test:
		run_doctest()
	else:
		run_calculator()
