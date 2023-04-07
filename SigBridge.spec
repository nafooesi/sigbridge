# -*- mode: python -*-

block_cipher = None


a = Analysis(['sig_bridge.py'],
             pathex=['C:\\Users\\vagrant\\Desktop\sigbridge'],
             binaries=[],
             datas=[
	        ('conf', 'conf'),
	     	('C:\\Python27\\lib\\site-packages\\ib', 'ib'),
			('C:\\Users\\vagrant\\Desktop\sigbridge\\fixapp', 'fixapp')
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
