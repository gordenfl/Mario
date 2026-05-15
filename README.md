# Super Mario Implementation in Python

This is inspired by Meth-Meth-Method's [super mario game](https://github.com/meth-meth-method/super-mario/)

## Running

* $ pip install -r requirements.txt
* $ python main.py

## Standalone windows build

* $ pip install py2exe
* $ python compile.py py2exe

## Controls

* Left: Move left  
* Right: Move right  
* Space: Jump  
* Shift: Boost
* Left/Right Mouseclick: secret

## Current state

![Alt text](img/pics.png "current state")

## Dependencies 

* pygame 
* scipy 

## Contribution

If you have any Improvements/Ideas/Refactors feel free to contact me or make a Pull Request.
The code needs still alot of refactoring as it is right now, so I appreciate any kind of Contribution.

MAC 上重装命令:

cd /Users/yiliu/Mario
./scripts/prepare_ios_app_folder.sh

xcodebuild -project ~/kivy-ios-work/mario-ios/mario.xcodeproj \
  -scheme mario -configuration Debug \
  -destination 'id=00008120-0010054E3C80201E' \
  -derivedDataPath ~/kivy-ios-work/DerivedData \
  -allowProvisioningUpdates build

xcrun devicectl device install app --device 00008120-0010054E3C80201E \
  ~/kivy-ios-work/DerivedData/Build/Products/Debug-iphoneos/mario.app

xcrun devicectl device process launch --device 00008120-0010054E3C80201E com.gordenfl.mario
