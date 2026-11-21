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

## ติดตั้งและรันบน Windows (ไดรฟ์ D:)

ติดตั้งเครื่องมือครั้งเดียว (PowerShell): Git, Python 3 + Pillow, ffmpeg (มี libass สำหรับซับ), Node.js (ไม่บังคับ ใช้ตัดคำไทยให้ซับคำต่อคำแม่นขึ้น)

```powershell
winget install Git.Git Python.Python.3.12 Gyan.FFmpeg OpenJS.NodeJS.LTS
py -m pip install pillow
```

ดึงโปรเจกต์ลงไดรฟ์ D:

```powershell
git clone -b claude/beautiful-goldberg-a1jt5q https://github.com/werawonglink1-hue/ollama-23.git D:\agent-office-workspace\video-studio\social-video-studio
```

- เปิด Claude Code (แอป Claude บนเดสก์ท็อป) ในโฟลเดอร์ `D:\agent-office-workspace\video-studio\social-video-studio` แล้ว skill และทีม agent 20 ตำแหน่งจะโหลดอัตโนมัติ
- เว็บ: ดับเบิลคลิก `video-studio-web\index.html` (Chrome/Edge)
- เรนเดอร์: `py .claude\skills\social-video-studio\scripts\render.py <project.json> --out out` (รองรับ path แบบ `D:\...` และชื่อไฟล์ภาษาไทยแล้ว)
