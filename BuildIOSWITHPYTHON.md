# Build iOS just use Python code

## Build ENV and Basic library

```shell
mkdir ios

cd ios

python3.11 -m venv venv

source venv/bin/activation

toolchain build python3 sdl2 sdl2_image sdl2_mixer sdl2_ttf kivy
```

Then you will get:

```txt
(venv) ➜  ios git:(udp) ✗ toolchain status  | grep Build
hostopenssl  - Build OK (built at 2026-05-02 06:17:22.458741)
hostpython3  - Build OK (built at 2026-05-02 06:20:26.504558)
ios          - Build OK (built at 2026-05-02 06:24:19.698478)
kivy         - Build OK (built at 2026-05-02 06:26:49.955946)
libffi       - Build OK (built at 2026-05-02 06:18:13.548552)
libpng       - Build OK (built at 2026-05-02 06:23:27.076983)
openssl      - Build OK (built at 2026-05-02 06:18:37.841924)
pyobjus      - Build OK (built at 2026-05-02 06:24:52.336241)
python3      - Build OK (built at 2026-05-02 06:22:31.116963)
sdl2         - Build OK (built at 2026-05-02 06:23:43.441658)
sdl2_image   - Build OK (built at 2026-05-02 06:23:48.846226)
sdl2_mixer   - Build OK (built at 2026-05-02 06:23:54.601047)
sdl2_ttf     - Build OK (built at 2026-05-02 06:24:09.050357)
```

## Generate xcode project

```bash
toolchain create mobile ../client
```

## Kivy client (recommended for iOS)

This repo now includes a Kivy-native client at `client_kivy/` that avoids `pygame`/`scipy` and is easier to package for iOS.

- **Local run (macOS)**:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r client_kivy/requirements.txt
python -m client_kivy
```

- **iOS packaging**:
  - Prefer packaging `client_kivy/` instead of `client/` when running `toolchain create mobile ...`.
  - The legacy pygame client depends on `scipy` for a blur effect; `scipy` makes iOS builds larger and less reliable.
  - The Kivy client uses touch controls: left half joystick (up=jump), right half tap=fire (landscape).

After that, you will get:

```txt
drwxr-xr-x@ 15 yiliu  staff  480 May  1 23:24 build
drwxr-xr-x@ 10 yiliu  staff  320 May  1 23:20 dist
drwxr-xr-x@ 11 yiliu  staff  352 May  1 23:32 mobile-ios
drwxr-xr-x@  6 yiliu  staff  192 May  1 21:03 venv
```

Open the xcode project with:

```shell
open mobile-ios/mobile.xcodeproj
```

change the code line

```python
chdir("YourApp");
```

into

```py
chdir("mobile");
```

## Setting in Xcode

after all that modification, you need change Build Phases of the project, click project then open 'Build Phases'
There are three Run Script Sections.

First one is :

```shell
rsync -av --delete "/Users/yiliu/Mario/client"/ "$PROJECT_DIR"/YourApp
```

change into :

```shell
rsync -av --delete "$PROJECT_DIR/../../client/" "$PROJECT_DIR/mobile"
```

And close the sandbox in the Build Settings. Search "ENABLE_USER_SCRIPT_SANDBOX" in Build Settings, set it to "NO"  
