# MKV Studio

MKV Studio is a Windows desktop app for combining a video with additional audio tracks and subtitles, then saving the result as an MKV file. It uses FFmpeg stream copy, so supported audio and video streams are not re-encoded.

![MKV Studio](icon.png)

## Features

- Remux MP4, MOV, AVI, WebM, TS and other supported formats to MKV.
- Add audio tracks in MKA, AAC, AC3, EAC3, DTS, MP3, FLAC, Opus, OGG, WAV, M4A and THD formats.
- Add SRT, ASS, SSA, VTT and SUP subtitles.
- Set each track's language, title and default flag. Audio tracks can also have a delay.
- Detect common languages from filenames, such as `movie.fr.srt` and `dub_arabic.mka`.
- Keep or remove the original audio and subtitles, and set the MKV title.
- Preserve attachments from the source MKV, including fonts used by ASS subtitles.
- Drag and drop files, view progress, cancel a job and inspect the FFmpeg log.

## Requirements

- Windows 10 or later.
- Python 3.10 or later to run from source or build the app.
- FFmpeg and FFprobe. They can be on `PATH`, in an `ffmpeg` folder beside the app, or selected in the app.

## Run from source

Double-click `build.bat` and choose **Run the app**. The script creates a local `.venv` environment and installs the Qt modules used by the app.

To set it up manually:

```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe main.py
```

Print the version without opening the window:

```powershell
python main.py --version
```

## Build for Windows

Run `build.bat` and choose **Build the Windows app**. PyInstaller creates a portable folder in `dist\MKV Studio\`. The build uses one-folder mode so the files are easier to inspect and troubleshoot.

To include FFmpeg in the portable build, place `ffmpeg.exe`, `ffprobe.exe` and the DLL files required by that build in an `ffmpeg` folder beside `build.bat`. Only the executables and DLLs are copied. Without bundled FFmpeg, users need to install it separately or select its folder in the app.

For a GitHub Release, zip the contents of `dist\MKV Studio\` and attach that archive to the release. Do not commit `.venv`, `build` or `dist` to the source repository. The local `ffmpeg/` folder is ignored by Git.

You can also run `build.bat run` or `build.bat build` from Command Prompt to skip the menu.

## Tests

Install the development requirements and run:

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest
```

The FFmpeg integration test is skipped when FFmpeg or FFprobe is not available.

## Notes

WebVTT and MP4 `mov_text` text subtitles are converted to SRT because Matroska does not support those subtitle formats directly.

## License

MKV Studio is licensed under the MIT License. PySide6-Essentials is distributed under its applicable license terms. FFmpeg is not included by default; check the license of any FFmpeg build before redistributing it.
