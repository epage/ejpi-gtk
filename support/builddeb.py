#!/usr/bin/python2.5

import os
import sys

import py2deb

import constants


__appname__ = constants.__app_name__
__description__ = "A Touch Screen Optimized RPN Calculator using Pie Menus"
__author__ = "Ed Page"
__email__ = "eopage@byu.net"
__version__ = constants.__version__
__build__ = 0
__changelog__ = '''
0.9.4
 * Added icons
 * Minor improvements
 * Swapping the keyboard positions, seem more friendly to my thumb location this way

0.9.3 - ""
 * Added +/-, !, sq, and sqrt functions
 * Improved Documentation
 * Copy of calculation result and the corresponding equation
 * Bug fixes

0.9.2 - ""
 * Experimenting with faster startup by including pyc files in package
 * Minor tweaks and bug fixes

0.9.1 - "Laziness doesn't always pay off"
 * Profiled the code with an especial focus on the pie menus
 * Tried to reduce potential bugs with double clicks
 * Fixed a visual artifact issue on popup

0.9.0 - "Feed is for horses, so what about feedback?"
 * Initial public release
 * Pie menus for keys
 * Modifiable history
 * Supports different number types and bases
 * Basic trig support
'''


__postinstall__ = '''#!/bin/sh

gtk-update-icon-cache /usr/share/icons/hicolor
'''


def find_files(path):
	for root, dirs, files in os.walk(path):
		for file in files:
			if file.startswith("src-"):
				fileParts = file.split("-")
				unused, relPathParts, newName = fileParts[0], fileParts[1:-1], fileParts[-1]
				assert unused == "src"
				relPath = os.sep.join(relPathParts)
				yield relPath, file, newName


def unflatten_files(files):
	d = {}
	for relPath, oldName, newName in files:
		if relPath not in d:
			d[relPath] = []
		d[relPath].append((oldName, newName))
	return d


if __name__ == "__main__":
	try:
		os.chdir(os.path.dirname(sys.argv[0]))
	except:
		pass

	p = py2deb.Py2deb(__appname__)
	p.description = __description__
	p.author = __author__
	p.mail = __email__
	p.license = "lgpl"
	p.depends = "python2.5, python2.5-gtk2"
	p.section = "user/accessories"
	p.arch = "all"
	p.urgency = "low"
	p.distribution = "chinook diablo"
	p.repository = "extras"
	p.changelog = __changelog__
	p.postinstall = __postinstall__
	p.icon="26x26-ejpi.png"
	p["/usr/bin"] = [ "ejpi.py" ]
	for relPath, files in unflatten_files(find_files(".")).iteritems():
		fullPath = "/usr/lib/ejpi"
		if relPath:
			fullPath += os.sep+relPath
		p[fullPath] = list(
			"|".join((oldName, newName))
			for (oldName, newName) in files
		)
	p["/usr/share/applications/hildon"] = ["ejpi.desktop"]
	p["/usr/share/icons/hicolor/26x26/hildon"] = ["26x26-ejpi.png|ejpi.png"]
	p["/usr/share/icons/hicolor/64x64/hildon"] = ["64x64-ejpi.png|ejpi.png"]
	p["/usr/share/icons/hicolor/scalable/hildon"] = ["scale-ejpi.png|ejpi.png"]

	print p
	print p.generate(
		__version__, __build__, changelog=__changelog__,
		tar=True, dsc=True, changes=True, build=False, src=True
	)
