# ทีม AI Agent 20 ตำแหน่ง (งานคอนเทนต์)

ทุกตำแหน่งเป็น subagent ใน `.claude/agents/<name>.md` เรียกได้ด้วยชื่อ เช่น "ให้ Content Creator เขียนสคริปต์คลิปเรื่อง..."
หรือผ่าน Agent tool ด้วย `subagent_type: content-creator`
**Claude หลัก (เซสชันที่คุยกับผู้ใช้) เป็นโปรดิวเซอร์**: แตกงาน เรียกตำแหน่งตามลำดับด้านล่าง ส่งไฟล์ต่อ และรวมรายงานให้ผู้ใช้

## ผังทีม

| ทำคลิป | โซเชียล | ภาพ/แบรนด์ | ข้อเสนอ/แอด | ทำเว็บ |
|---|---|---|---|---|
| Short-Video Editing Coach | Instagram Curator | Visual Storyteller | Offer & Lead Gen Strategist | Frontend Developer |
| Video Optimization Specialist | TikTok Strategist | Brand Guardian | Ad Creative Strategist | Code Reviewer |
| Content Creator | Carousel Growth Engine | Image Prompt Engineer | Pricing Analyst | Minimal Change Engineer |
| Reality Checker | Growth Hacker | UI Designer | Paid Social Strategist | Security Auditor |

## ใครทำอะไรในโปรเจกต์นี้

| ตำแหน่ง | `name` | งานหลัก | ส่งออก | สิทธิ์ |
|---|---|---|---|---|
| Content Creator | `content-creator` | แผนซีรีส์ 1–5 คลิป + สคริปต์ `/ // ///` ทุกสไตล์ผู้เล่า | `brief.md`, `sources.md`, `scripts/clipN.txt` | เขียน |
| Reality Checker | `reality-checker` | ตรวจข้อเท็จจริง + ตรวจว่างาน "เสร็จจริง" มีหลักฐาน | `qa/reality-check.md` | เขียนเฉพาะ `qa/` |
| Short-Video Editing Coach | `short-video-editing-coach` | จังหวะ ซับ เสียง ประกอบ project.json เรนเดอร์ ดูเฟรม | `project.json`, `out/*.mp4 .srt .ass` | เขียน |
| Video Optimization Specialist | `video-optimization-specialist` | สเปกแพลตฟอร์ม ความดัง safe zone ปก ชื่อ ไทม์สแตมป์ | `qa/optimization.md`, ปก | เขียน |
| Visual Storyteller | `visual-storyteller` | สตอรีบอร์ด บรรทัดฉาก ป้าย/หัวข้อ/ภาพ/โทน/สี | `storyboard/clipN.md` | เขียน |
| Image Prompt Engineer | `image-prompt-engineer` | character sheet + prompt ภาพ/วิดีโอ AI ต่อฉาก | `prompts/` | เขียน |
| Brand Guardian | `brand-guardian` | brand guide + ตรวจแบรนด์/ลิขสิทธิ์ก่อนเผยแพร่ | `work/brand-guide.md`, `qa/brand-check.md` | เขียน |
| UI Designer | `ui-designer` | หน้าตาและการใช้งานเว็บตัดต่อ | `work/web/ui-spec-*.md` | เขียน (CSS เล็กน้อย) |
| TikTok Strategist | `tiktok-strategist` | hook บนจอ ปก แคปชัน แฮชแท็ก ซีรีส์ | `posts/clipN-tiktok.md` | เขียน |
| Instagram Curator | `instagram-curator` | Reels/ฟีด แคปชัน แฮชแท็ก ปกบนกริด alt text | `posts/clipN-instagram.md` | เขียน |
| Carousel Growth Engine | `carousel-growth-engine` | แปลงคลิปเป็นคารูเซล 5–10 สไลด์ | `carousel/` | เขียน |
| Growth Hacker | `growth-hacker` | แผนทดลอง ตัวชี้วัด อ่านผล analytics | `growth/experiments.md` | เขียน |
| Offer & Lead Gen Strategist | `offer-lead-gen-strategist` | ข้อเสนอ CTA ของแจก DM landing | `offers/offer.md` | เขียน |
| Ad Creative Strategist | `ad-creative-strategist` | แอดหลายเวอร์ชันในรูปแบบสคริปต์ที่เรนเดอร์ได้ | `ads/clipN-vK.txt`, `ads/ads-project.json` | เขียน |
| Paid Social Strategist | `paid-social-strategist` | โครงแคมเปญ งบ แผนทดสอบ อ่านผลแอด | `ads/campaign-plan.md` | เขียน |
| Pricing Analyst | `pricing-analyst` | ต้นทุนต่อคลิป แพ็กเกจราคา กำไร | `work/pricing/pricing.md` | เขียน |
| Frontend Developer | `frontend-developer` | พัฒนา `video-studio-web/index.html` ให้ตรงกับ Python | โค้ด + ผลทดสอบ Playwright | เขียน |
| Code Reviewer | `code-reviewer` | รีวิว diff หาบั๊กจริง + parity เว็บ↔Python | รายงาน (ส่งกลับให้โปรดิวเซอร์) | อ่านอย่างเดียว |
| Minimal Change Engineer | `minimal-change-engineer` | แก้บั๊กด้วย diff เล็กที่สุด + ทดสอบซ้ำ | diff + หลักฐาน | แก้ไฟล์เดิม |
| Security Auditor | `security-auditor` | ตรวจความปลอดภัยเว็บ + สคริปต์ Python | รายงาน (ส่งกลับให้โปรดิวเซอร์) | อ่านอย่างเดียว |

## สายงาน (ลำดับการส่งต่อ)

### A) ทำคลิปจาก brief เดียว (1–5 คลิป)
```
Content Creator ─► Reality Checker ─► Visual Storyteller ─► Image Prompt Engineer ─► Brand Guardian
 (แผน+สคริปต์        (ข้อเท็จจริง)       (บรรทัดฉาก)            (prompt ภาพ)            (แบรนด์/ลิขสิทธิ์)
  ×N คลิปขนานกัน)                                                                       │
                                                                                         ▼
          Reality Checker ◄── Video Optimization Specialist ◄── Short-Video Editing Coach
          (ไฟล์จริง เฟรม ซับครบ)   (สเปก ความดัง ปก)               (ซับ เสียง เรนเดอร์ 9:16+16:9)
```

### B) ลงโซเชียล (หลังคลิปผ่าน Reality Checker)
```
TikTok Strategist ─┐
Instagram Curator ─┼─(ขนานกัน)─► Brand Guardian ─► Growth Hacker (แผนทดลอง/วัดผล) ─► วนกลับ Content Creator
Carousel Growth Engine ─┘
```

### C) ข้อเสนอและโฆษณา
```
Pricing Analyst ─► Offer & Lead Gen Strategist ─► Ad Creative Strategist ─► Short-Video Editing Coach (เรนเดอร์แอด)
                                                                         └─► Paid Social Strategist (แผนแคมเปญ)
```

### D) ทำเว็บ (`video-studio-web`)
```
UI Designer ─► Frontend Developer ─► Code Reviewer ┐
                                  └► Security Auditor ┴─(ขนานกัน)─► Minimal Change Engineer ─► Reality Checker
```

## กติการ่วมของทีม

- ไม่มีงานไหนถึงมือผู้ใช้โดยไม่ผ่าน **Reality Checker** และคำว่า "เสร็จ/ผ่าน" ต้องมีหลักฐาน (คำสั่งที่รัน + ผลลัพธ์ หรือภาพ)
- การกระทำภายนอก (โพสต์จริง ยิงแอด ใช้เงิน ส่งข้อความหาลูกค้า) ผู้ใช้ต้องอนุมัติและทำเอง ทีมเตรียมไฟล์และแผนให้เท่านั้น
- ข้อเท็จจริงของคนจริงต้องมีแหล่งอ้างอิง ห้ามแต่งตัวเลข · ภาพต้องมีสิทธิ์ใช้และมีเครดิต · ไม่แอบอ้างบุคคลจริง
- ตำแหน่งที่ทำงานขนานกันได้: Content Creator หลายคลิป · โซเชียล 3 ตำแหน่ง · Code Reviewer + Security Auditor

## โฟลเดอร์ทำงาน

```
work/
  brand-guide.md               Brand Guardian
  pricing/pricing.md           Pricing Analyst
  web/                         รายงานแผนกทำเว็บ (ui-spec, review, security)
  <slug>/                      1 brief = 1 โฟลเดอร์
    brief.md  sources.md       Content Creator
    scripts/clipN.txt          Content Creator (+ บรรทัดฉากจาก Visual Storyteller)
    storyboard/  prompts/      Visual Storyteller, Image Prompt Engineer
    media/                     รูป/วิดีโอ/เสียงพากย์ (ผู้ใช้หรือเครื่องมือสร้างภาพ)
    project.json  out/         Short-Video Editing Coach
    qa/                        Reality Checker, Brand Guardian, Video Optimization Specialist
    posts/  carousel/  growth/ แผนกโซเชียล
    offers/  ads/              แผนกข้อเสนอ/แอด
```

## Skill ที่มีอยู่แล้วและตำแหน่งที่ดึงไปใช้ (ถ้าเปิดใช้งานในเครื่องนั้น)

| Skill | ตำแหน่ง |
|---|---|
| `social-video-studio` (skill นี้) | ทุกตำแหน่ง |
| `artifact-design`, `design:accessibility-review`, `design:design-critique` | UI Designer |
| `design:ux-copy` | UI Designer, Offer & Lead Gen Strategist |
| `design:design-system` | Brand Guardian |
| `run`, `claude-api`, `anthropic-skills:web-artifacts-builder` | Frontend Developer |
| `code-review`, `engineering:code-review` | Code Reviewer |
| `engineering:debug` | Minimal Change Engineer |
| `security-review` | Security Auditor |
| `brightdata-plugin:brand-listening`, `brightdata-plugin:competitive-intel` | Growth Hacker, Pricing Analyst |
| `brightdata-plugin:price-comparison`, `anthropic-skills:xlsx` | Pricing Analyst |

## เทียบกับทีมเดิม 5 ตำแหน่ง (รวมเข้าทีมนี้แล้ว)

video-director → Claude หลัก (โปรดิวเซอร์) + Content Creator (แผนซีรีส์) ·
story-scriptwriter → Content Creator ·
art-director → Visual Storyteller + Image Prompt Engineer ·
subtitle-sound-engineer + video-editor → Short-Video Editing Coach + Video Optimization Specialist
