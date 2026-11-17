# 🎨 Spin the Wheel – Color Picker

Add colors and names, then each person spins the wheel to get their color.
"Balanced colors" mode keeps the final totals even while the order stays random.
Results can be saved as an image.

## ⬇️ Download (Windows)

**[Download SpinTheWheel.exe](https://github.com/rrwebsolution/spin-the-wheel/releases/latest/download/SpinTheWheel.exe)**,
then double-click it. You don't need Python.

> If Windows shows **"Windows protected your PC"**, click **More info → Run anyway**.
> This appears because the app isn't code-signed.

## Run from source

```bash
pip install -r requirements.txt
python main.py
```

## How the .exe is built

Every push to `master` makes GitHub Actions ([build-exe.yml](.github/workflows/build-exe.yml))
build a new `SpinTheWheel.exe` and publish it on the
[Releases](https://github.com/rrwebsolution/spin-the-wheel/releases) page.
