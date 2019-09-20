# -*- mode: python -*-

block_cipher = None


a = Analysis(['SigBridge.py'],
             pathex=['C:\\Users\\IEUser\\Desktop\sigbridge'],
             binaries=[],
             datas=[
	        ('conf', 'conf'),
	     	('C:\\python27\\lib\\site-packages\\ib', 'ib')
		],
             hiddenimports=[],
             hookspath=[],
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          exclude_binaries=True,
          name='SigBridge',
          icon='SigBridge.ico',
          debug=False,
          strip=False,
          upx=True,
          console=False)
coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               strip=False,
               upx=True,
               name='SigBridge')
