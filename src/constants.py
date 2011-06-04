import os

__pretty_app_name__ = "e**(j pi) + 1 = 0"
__app_name__ = "ejpi-gtk"
__version__ = "0.9.9"
__build__ = 0
__app_magic__ = 0xdeadbeef
_data_path_ = os.path.join(os.path.expanduser("~"), ".%s" % __app_name__)
_user_settings_ = "%s/settings.ini" % _data_path_
_user_logpath_ = "%s/%s.log" % (_data_path_, __app_name__)
