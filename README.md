# Social Video Studio: สตูดิโอคลิปเล่าเรื่องภาษาไทย

| ส่วน | ที่อยู่ |
|---|---|
| เว็บตัดต่อ (เปิด `index.html` ใน Chrome/Edge) | [`video-studio-web/`](video-studio-web/README.md) |
| Skill สำหรับ Claude Code | [`.claude/skills/social-video-studio/`](.claude/skills/social-video-studio/SKILL.md) |
| ทีม AI Agent 20 ตำแหน่ง (ทำคลิป · โซเชียล · ภาพ/แบรนด์ · ข้อเสนอ/แอด · ทำเว็บ) | [`.claude/agents/`](.claude/agents/) · ผังทีม [`team.md`](.claude/skills/social-video-studio/references/team.md) |

กรอกข้อมูลครั้งเดียวได้ 1–5 คลิป ค่าเริ่มต้นเป็นแบบ "สารคดีคอลลาจ" ตามคลิปตัวอย่างพื้นฐาน
(ป้ายปี หัวข้อ ขอบกระดาษฉีก ซับเด้งคำต่อคำ) และเลือกสไตล์อื่นได้จากดรอปดาวน์ เช่น เล่าเรื่องละมุน ครูหน่อง มานะ
ส่งออกได้ทั้งแนวตั้ง 9:16 และแนวนอน 16:9

เรนเดอร์ด้วย ffmpeg:

```bash
python3 .claude/skills/social-video-studio/scripts/render.py .claude/skills/social-video-studio/templates/project.example.json --out out/
```

## สกิลเสริมเสียงและภาพ

| สกิล | ทำอะไร | ค่าใช้จ่าย |
|---|---|---|
| [`higgsfield-studio`](.claude/skills/higgsfield-studio/SKILL.md) | เสียงพากย์ไทย AI ที่เว้นจังหวะตามสคริปต์ + ซับตรงเสียง, ภาพ AI ต่อฉาก, ตัดพื้นหลังเป็นสติกเกอร์, เตรียมโพสต์ TikTok | เครดิต Higgsfield (ขออนุมัติก่อนทุกครั้ง) |
| [`web-image-research`](.claude/skills/web-image-research/SKILL.md) | หาภาพจริงจาก Wikimedia Commons / Openverse ที่ใช้ได้ถูกลิขสิทธิ์ ใส่เครดิตบนการ์ดให้เอง | ฟรี |
| [`comfyui-scenes`](.claude/skills/comfyui-scenes/SKILL.md) | ภาพ AI จาก ComfyUI บน GPU ของเราเอง | ฟรี |
| [`auto-editor`](.claude/skills/auto-editor/SKILL.md) | ตัดช่วงเงียบเสียงที่อัดเอง ถอดเวลาคำ ส่งงานเข้า Resolve/Premiere | ฟรี |
| [`audiocraft-music`](.claude/skills/audiocraft-music/SKILL.md) | เพลง/เสียงประกอบ AI บนเครื่องตัวเอง | ฟรี แต่ห้ามใช้กับงานหารายได้ (CC BY-NC) |
| [`agent-reach`](.claude/skills/agent-reach/SKILL.md) | อ่านข้อมูล ซับ คอมเมนต์ จาก YouTube/Reddit/X ฯลฯ เพื่อหาเรื่องและตรวจข้อเท็จจริง (อ่านอย่างเดียว) | ฟรี |
| [`trading-agent-architecture`](.claude/skills/trading-agent-architecture/SKILL.md) | เอกสารสถาปัตยกรรมบอทเทรดหลาย Agent (คนละโปรเจกต์กับงานคลิป) | — |

ขั้นตอนเสียงพากย์จริง: สร้างเสียง (Higgsfield หรืออัดเอง) → `whisper_words.py` → `voice_align.py assemble` → `render.py`
(รายละเอียดใน [`higgsfield-studio/SKILL.md`](.claude/skills/higgsfield-studio/SKILL.md))

## ติดตั้งและรันบน Windows (ไดรฟ์ D:)

ติดตั้งเครื่องมือครั้งเดียว (PowerShell): Git, Python 3 + Pillow, ffmpeg (มี libass สำหรับซับ), Node.js (ไม่บังคับ ใช้ตัดคำไทยให้ซับคำต่อคำแม่นขึ้น)

```powershell
winget install Git.Git
winget install Python.Python.3.12
winget install Gyan.FFmpeg
winget install OpenJS.NodeJS.LTS
py -m pip install pillow
```

ดึงโปรเจกต์ลงไดรฟ์ D:

```powershell
git clone -b claude/beautiful-goldberg-a1jt5q https://github.com/werawonglink1-hue/ollama-23.git D:\agent-office-workspace\video-studio\social-video-studio
```

- เปิด Claude Code (แอป Claude บนเดสก์ท็อป) ในโฟลเดอร์ `D:\agent-office-workspace\video-studio\social-video-studio` แล้ว skill และทีม agent 20 ตำแหน่งจะโหลดอัตโนมัติ
- เว็บ: ดับเบิลคลิก `video-studio-web\index.html` (Chrome/Edge)
- เรนเดอร์: `py .claude\skills\social-video-studio\scripts\render.py <project.json> --out out` (รองรับ path แบบ `D:\...` และชื่อไฟล์ภาษาไทยแล้ว)

เครื่องมือเสริม (ติดตั้งเฉพาะที่ใช้):

```powershell
py -m pip install faster-whisper
```

```powershell
py -m pip install auto-editor
```

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

```powershell
uv tool install https://github.com/Panniantong/Agent-Reach/releases/latest/download/agent-reach.zip
```

- `faster-whisper`: เวลาแต่ละคำของเสียงพากย์ (ใช้กับ `voice_align.py`) · `auto-editor`: ตัดช่วงเงียบ/ถอดเสียง · `uv` + Agent Reach: อ่านข้อมูลจากแพลตฟอร์ม (หลังติดตั้งรัน `agent-reach setup`)
- Higgsfield: เชื่อม Higgsfield ใน Claude (Connectors) แล้ว Claude เรียกใช้ให้ได้เลย ไม่ต้องติดตั้งอะไรในเครื่อง
- ComfyUI และ AudioCraft แนะนำการ์ดจอ NVIDIA (ใช้ CPU ได้แต่ช้ามาก) ดูวิธีติดตั้งใน `comfyui-scenes/SKILL.md` และ `audiocraft-music/SKILL.md`
