"""Small real render/export check; does not claim visual or native-AE validation."""
from pathlib import Path
import copy
import json
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "remake-reference-video" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import video_pipeline as pipeline
from font_setup import ensure_font, verify_bytes

def run(*args):
    subprocess.run([str(x) for x in args], check=True)

def main():
    font_path = ensure_font()
    assert ensure_font() == font_path
    altered = bytearray(font_path.read_bytes())
    altered[-1] ^= 1
    try:
        verify_bytes(bytes(altered))
    except ValueError:
        pass
    else:
        raise AssertionError("Corrupt font was accepted")
    with tempfile.TemporaryDirectory(prefix="reference-video-smoke-") as folder:
        job = Path(folder)
        frames = job / "frames"
        frames.mkdir()
        for i in range(8):
            im = Image.new("RGB", (320, 568), (12, 25, 65))
            ImageDraw.Draw(im).ellipse((30+i, 100, 290+i, 360), outline=(235, 190, 70), width=2)
            im.save(frames / f"f_{i+1:06d}.png")
        plan = {
            "version": 1,
            "source": {"frame_dir": "frames", "width": 320, "height": 568, "fps": "24000/1001", "frames": 8},
            "output": {"width": 320, "height": 568, "fps": "24000/1001", "background": [12, 25, 65]},
            "replacements": [{"id": "s1", "start": 0, "end": 8, "cn": "一路陪你", "en": "HEALTH CARE 96%+"}],
            "layers": [
                {"id": "cn", "slot": "s1", "language": "zh", "text": "一路陪你", "font_size": 45, "in": 0, "out": 8,
                 "keys": [[0, 160, 235, .8, .8, 0, 1, 0], [3, 160, 235, 1, 1, 0, 1, 0]]},
                {"id": "en", "slot": "s1", "language": "en", "text": "HEALTH CARE 96%+", "font_size": 15, "in": 0, "out": 8,
                 "keys": [[0, 160, 300, 1, 1, 0, 1, 0]]}
            ]
        }
        path = job / "plan.json"
        path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
        parsed = pipeline.load_plan(path)
        assert parsed["font"]["postscript"] == "NotoSansCJKsc-Bold"
        pipeline.validate(parsed)
        custom = copy.deepcopy(plan)
        custom["font"] = {"path": str(font_path)}
        custom_path = job / "custom.json"
        custom_path.write_text(json.dumps(custom), encoding="utf-8")
        original_default = pipeline.default_font
        def no_download():
            raise AssertionError("Explicit font must not fetch a default font")
        pipeline.default_font = no_download
        try:
            pipeline.validate(pipeline.load_plan(custom_path))
        finally:
            pipeline.default_font = original_default
        broken = copy.deepcopy(parsed)
        broken["layers"][1]["text"] = "HEALTH CARE 96%"
        try:
            pipeline.validate(broken)
        except ValueError as error:
            assert "Copy mismatch" in str(error)
        else:
            raise AssertionError("Missing punctuation was not detected")
        wrong_font = copy.deepcopy(plan)
        wrong_font["font"] = {"path": str(font_path), "postscript": "WRONG-FONT"}
        wrong_path = job / "wrong_font.json"
        wrong_path.write_text(json.dumps(wrong_font), encoding="utf-8")
        try:
            pipeline.load_plan(wrong_path)
        except ValueError:
            pass
        else:
            raise AssertionError("Incorrect PostScript name was accepted")
        run(sys.executable, SCRIPTS / "video_pipeline.py", "render", "--plan", path, "--output", job / "final.mp4")
        run(sys.executable, SCRIPTS / "video_pipeline.py", "verify", "--plan", path, "--video", job / "final.mp4", "--report", job / "report.json")
        report = json.loads((job / "report.json").read_text(encoding="utf-8"))
        assert report["media"]["frames"] == 8 and report["media"]["audio_streams"] == 0
        assert report["media"]["native_ae_render_verified"] is False
        run(sys.executable, SCRIPTS / "export_ae.py", "--plan", path, "--output", job / "ae")
        ae = job / "ae"
        assert (ae / "OFL.txt").read_text(encoding="utf-8") == (SCRIPTS.parent / "assets/fonts/OFL.txt").read_text(encoding="utf-8")
        assert (ae / "FONT-NOTICE.txt").is_file()
        assert (ae / font_path.name).is_file()
        run("node", "-e", "new (require('vm').Script)(require('fs').readFileSync(process.argv[1], 'utf8'));", ae / "Run_in_After_Effects.jsx")
        print("PASS: font integrity/cache, copy checks, real render/decode, silent media, AE JSX and OFL export.")
        print("Native AE execution and visual fidelity are not claimed by this smoke check.")

if __name__ == "__main__":
    main()
