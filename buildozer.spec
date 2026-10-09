[app]
title = Pocket Mahjong
package.name = pocketmahjong
package.domain = com.hoveybits

source.dir = .
source.include_exts = py,kv,png,jpg

version = 1.0.0
android.numeric_version = 1

requirements = python3,kivy

orientation = all
fullscreen = 1

icon.filename = %(source.dir)s/icon.png

android.archs = arm64-v8a
android.minapi = 26
android.api = 36

[buildozer]
log_level = 2
warn_on_root = 1
