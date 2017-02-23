## What is this?
This is a python application with minimal UI that replicates trade signals from TradeStation to one or more Interactivebroker clients.

## Dependencies:
-ibpy2
-pyinstaller

## Configuration:
IB clients are configured in a json file under "conf" dir. 
The attributes in the config file should be self explainatory.

## Run & Test:
Run:  
python SigBridge.py

Tests:  (sending simulated trade signal as if it's from TradeStation)  
python tests/SendSig.py 

## Build & Distribute
To create distributable app, run:  
pyinstaller Sigbridge.spec

The distributable folder will be under the resulting "dist" dir.  
I choose to not use "one file" executable distribution, because: 
- There's an issue with ibpy2 lib import when packaged into an extractable executable.
- One file executable is less secure and takes longer to start since it needs to extract all files to a temp dir at run time before executing the main program.

