"""
ai_features/report_generator.py
================================
Generates a USER-FRIENDLY PDF summary report.

Focus: What happened in the video — plain English for students,
professionals, and content creators. NO ML jargon.

Install:  pip install reportlab
"""

import os
from typing import List, Dict, Optional
from datetime import datetime
from collections import Counter


# ─────────────────────────── AI summary generator ────────────────────────

def generate_ai_summary(
        transcript:    Optional[Dict],
        segments:      List,
        seg_scores:    List[float],
        keyword_hits:  Optional[List],
        face_data:     Optional[List],
        emotion_data:  Optional[List],
        video_info:    Dict,
        highlight_meta:Dict,
        video_filename:str,
) -> Dict:
    """
    Build a plain-English summary of the video without any ML jargon.
    Returns a dict of summary sections used in the PDF.
    """
    duration      = video_info.get("duration", 0)
    hl_duration   = highlight_meta.get("highlight_duration", 0)
    n_segs        = len(segments)
    compression   = round((1 - hl_duration / max(duration, 1)) * 100) if duration else 0

    # ── What the video is about (from transcript) ──
    topic_summary = ""
    key_sentences = []
    word_freq     = {}

    if transcript and transcript.get("text"):
        full_text  = transcript["text"].strip()
        # Extract first meaningful sentence as topic
        sentences  = [s.strip() for s in full_text.replace("?","!").split(".") if len(s.strip()) > 20]
        if sentences:
            topic_summary = sentences[0]

        # Find most repeated meaningful words (topic keywords)
        stop = {"the","a","an","and","or","but","in","on","at","to","for","of","with",
                "is","are","was","were","it","this","that","we","you","i","he","she",
                "they","be","have","has","do","did","not","so","if","as","from","by",
                "its","their","our","my","your","will","can","could","would","should",
                "let","just","now","then","there","here","when","what","how","which",
                "also","more","like","about","up","out","into","than","these","those"}
        words = [w.lower().strip(".,!?\"'") for w in full_text.split()
                 if len(w) > 4 and w.lower().strip(".,!?\"'") not in stop]
        word_freq = dict(Counter(words).most_common(8))

        # Pick 3 best sentences from keyword-hit segments
        if keyword_hits:
            seen = set()
            for hit in keyword_hits[:10]:
                txt = hit.get("text","").strip()
                if txt and txt not in seen and len(txt) > 15:
                    key_sentences.append({"time": hit["time"], "text": txt})
                    seen.add(txt)
                if len(key_sentences) >= 5:
                    break

    # ── Presenter analysis ──
    presenter_visible = False
    top_emotion       = "neutral"
    if face_data:
        face_pct = sum(1 for f in face_data if f.get("has_face")) / max(len(face_data),1) * 100
        presenter_visible = face_pct > 20
    if emotion_data:
        ec = Counter(e["dominant_emotion"] for e in emotion_data)
        top_emotion = ec.most_common(1)[0][0] if ec else "neutral"

    # ── Video type detection ──
    video_type = _detect_video_type(video_filename, transcript, word_freq)

    # ── Generate highlight map ──
    highlight_map = []
    for i, (s, e) in enumerate(segments):
        conf  = seg_scores[i] if i < len(seg_scores) else 0
        label = _label_segment(i, s, e, transcript, keyword_hits, conf)
        highlight_map.append({
            "index":    i + 1,
            "start":    s,
            "end":      e,
            "duration": e - s,
            "label":    label,
            "confidence": conf,
        })

    return {
        "topic_summary":      topic_summary,
        "key_sentences":      key_sentences,
        "word_freq":          word_freq,
        "video_type":         video_type,
        "compression":        compression,
        "n_segments":         n_segs,
        "duration":           duration,
        "hl_duration":        hl_duration,
        "presenter_visible":  presenter_visible,
        "top_emotion":        top_emotion,
        "highlight_map":      highlight_map,
        "has_transcript":     bool(transcript and transcript.get("text")),
        "transcript_text":    (transcript or {}).get("text", ""),
        "transcript_language":(transcript or {}).get("language", ""),
        "keyword_hits":       keyword_hits or [],
    }


def _detect_video_type(filename, transcript, word_freq):
    """Guess whether it's a lecture, tutorial, meeting, kids video, etc."""
    name = filename.lower()
    text = (transcript or {}).get("text","").lower() if transcript else ""
    combined = name + " " + text

    if any(w in combined for w in ["lecture","class","course","university","lesson","study"]):
        return "Educational Lecture"
    if any(w in combined for w in ["tutorial","how to","step by step","guide","install"]):
        return "Tutorial / How-To"
    if any(w in combined for w in ["meeting","webinar","agenda","team","project","update"]):
        return "Meeting / Webinar"
    if any(w in combined for w in ["kids","children","learn","animal","cartoon","school"]):
        return "Kids Learning Video"
    if any(w in combined for w in ["review","unbox","product","demo"]):
        return "Product Demo / Review"
    return "General Video"


def _label_segment(idx, start, end, transcript, keyword_hits, confidence):
    """Give each segment a short descriptive label based on what's spoken."""
    # Check if a keyword hit falls in this segment
    if keyword_hits:
        for hit in keyword_hits:
            if start <= hit["time"] <= end:
                kw = hit.get("keyword","").title()
                return f"Key Point: {kw}"

    # Try to get first few words from transcript
    if transcript and transcript.get("segments"):
        for seg in transcript["segments"]:
            if start <= seg["start"] <= end:
                txt = seg["text"].strip()
                if len(txt) > 5:
                    words = txt.split()[:6]
                    return " ".join(words) + "…"

    # Fallback by position
    labels = ["Opening / Introduction", "Early Content", "Main Discussion",
              "Key Explanation", "Important Section", "Core Content",
              "Detailed Explanation", "Examples / Demo", "Advanced Topic",
              "Summary / Conclusion"]
    return labels[min(idx, len(labels)-1)]


# ─────────────────────────── PDF generator ───────────────────────────────

def generate_report(
        output_path:    str,
        video_filename: str,
        video_info:     Dict,
        highlight_meta: Dict,
        segments:       List,
        seg_scores:     List[float],
        timeline:       List[Dict],
        transcript:     Optional[Dict] = None,
        face_data:      Optional[List] = None,
        emotion_data:   Optional[List] = None,
        keyword_hits:   Optional[List] = None,
        ml_metrics:     Optional[Dict] = None,
) -> str:
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib           import colors
        from reportlab.lib.styles    import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units     import cm
        from reportlab.platypus      import (SimpleDocTemplate, Paragraph,
                                              Spacer, Table, TableStyle,
                                              HRFlowable, KeepTogether)
    except ImportError:
        raise RuntimeError("reportlab not installed. Run: pip install reportlab")

    # Build the AI summary first
    summary = generate_ai_summary(
        transcript, segments, seg_scores, keyword_hits,
        face_data, emotion_data, video_info, highlight_meta, video_filename
    )

    doc   = SimpleDocTemplate(str(output_path), pagesize=A4,
                               leftMargin=2*cm, rightMargin=2*cm,
                               topMargin=2*cm,  bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    story  = []

    # ── colour palette ──
    GREEN  = colors.HexColor("#00c96e")
    DARK   = colors.HexColor("#111318")
    MUTED  = colors.HexColor("#6b7180")
    BLUE   = colors.HexColor("#0077cc")
    YELLOW = colors.HexColor("#f59e0b")
    LIGHT  = colors.HexColor("#f0fdf4")

    def sp(h=8):   return Spacer(1, h)
    def hr():
        return HRFlowable(width="100%", thickness=1,
                          color=colors.HexColor("#e0e0e0"), spaceAfter=6)

    title_s = ParagraphStyle("T", parent=styles["Title"],
                              fontSize=24, textColor=DARK, spaceAfter=2)
    h2_s    = ParagraphStyle("H2", parent=styles["Heading2"],
                              fontSize=13, textColor=DARK, spaceBefore=10, spaceAfter=4)
    h3_s    = ParagraphStyle("H3", parent=styles["Heading3"],
                              fontSize=11, textColor=BLUE, spaceBefore=6, spaceAfter=3)
    body_s  = ParagraphStyle("B", parent=styles["Normal"],
                              fontSize=10, leading=15, spaceAfter=4)
    muted_s = ParagraphStyle("M", parent=body_s, textColor=MUTED, fontSize=9)
    bold_s  = ParagraphStyle("Bold", parent=body_s, fontName="Helvetica-Bold")
    quote_s = ParagraphStyle("Q", parent=body_s,
                              leftIndent=16, textColor=colors.HexColor("#374151"),
                              borderPad=6, fontSize=10, leading=15,
                              backColor=colors.HexColor("#f9fafb"))

    def fmt(s):
        s = int(s or 0); m = s//60
        return f"{m}m {s%60:02d}s" if m else f"{s}s"

    # ═══════════════════════════════════════════════════════
    # HEADER
    # ═══════════════════════════════════════════════════════
    story.append(Paragraph("▶ HILIGHT", title_s))
    story.append(Paragraph("Video Analysis Report",
                            ParagraphStyle("sub", parent=muted_s, fontSize=12)))
    story.append(sp(3))
    story.append(Paragraph(
        f"<b>File:</b> {video_filename} &nbsp;&nbsp; "
        f"<b>Generated:</b> {datetime.now().strftime('%Y-%m-%d %H:%M')} &nbsp;&nbsp; "
        f"<b>Type:</b> {summary['video_type']}",
        muted_s))
    story.append(hr())

    # ═══════════════════════════════════════════════════════
    # SECTION 1 — VIDEO OVERVIEW (plain English)
    # ═══════════════════════════════════════════════════════
    story.append(Paragraph("📋 Video Overview", h2_s))

    dur_min  = int(summary["duration"]) // 60
    hl_min   = int(summary["hl_duration"]) // 60
    hl_sec   = int(summary["hl_duration"])  % 60
    saved    = summary["duration"] - summary["hl_duration"]

    overview_text = (
        f"This is a <b>{summary['video_type']}</b> that runs for "
        f"<b>{fmt(summary['duration'])}</b>. "
        f"The AI analysed every frame and identified the <b>{summary['n_segments']} most "
        f"important moments</b>, which were compiled into a "
        f"<b>{fmt(summary['hl_duration'])} highlight</b> — "
        f"saving you <b>{fmt(saved)}</b> of watching time "
        f"(<b>{summary['compression']}% shorter</b> than the original)."
    )
    story.append(Paragraph(overview_text, body_s))

    # Presenter / emotion note
    if summary["presenter_visible"]:
        emotion_desc = {
            "happy":    "engaged and enthusiastic",
            "surprise": "animated and expressive",
            "neutral":  "calm and focused",
            "sad":      "serious",
            "angry":    "intense",
        }.get(summary["top_emotion"], "focused")
        story.append(Paragraph(
            f"👤 A presenter is visible throughout the video and appears "
            f"<b>{emotion_desc}</b> in most segments.",
            body_s))

    story.append(sp())

    # Quick stats table
    stats = [
        ["📹 Original Duration", fmt(summary["duration"]),
         "✂️ Highlight Duration", fmt(summary["hl_duration"])],
        ["📌 Key Segments Found", str(summary["n_segments"]),
         "⏱️ Time Saved", fmt(saved)],
        ["🗜️ Compression",       f"{summary['compression']}%",
         "🎬 Video Type",         summary["video_type"]],
    ]
    t = Table(stats, colWidths=[4.5*cm, 3.5*cm, 4.5*cm, 3.5*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), LIGHT),
        ("BACKGROUND",    (0,0), (0,-1), colors.HexColor("#dcfce7")),
        ("BACKGROUND",    (2,0), (2,-1), colors.HexColor("#dcfce7")),
        ("FONTNAME",      (0,0), (0,-1), "Helvetica-Bold"),
        ("FONTNAME",      (2,0), (2,-1), "Helvetica-Bold"),
        ("FONTSIZE",      (0,0), (-1,-1), 9),
        ("GRID",          (0,0), (-1,-1), 0.5, colors.HexColor("#d1fae5")),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 8),
    ]))
    story.append(t)
    story.append(sp())

    # ═══════════════════════════════════════════════════════
    # SECTION 2 — WHAT THIS VIDEO IS ABOUT
    # ═══════════════════════════════════════════════════════
    story.append(hr())
    story.append(Paragraph("🔍 What This Video Is About", h2_s))

    if summary["has_transcript"]:
        if summary["topic_summary"]:
            story.append(Paragraph("The video begins with:", bold_s))
            story.append(Paragraph(f'"{summary["topic_summary"]}"', quote_s))
            story.append(sp(4))

        if summary["word_freq"]:
            top_words = list(summary["word_freq"].keys())[:6]
            story.append(Paragraph(
                f"The most discussed topics in this video include: "
                f"<b>{', '.join(top_words)}</b>.",
                body_s))
    else:
        story.append(Paragraph(
            "⚠️ Speech-to-text was not enabled for this analysis. "
            "Enable Whisper AI and re-process the video to get a full description "
            "of what is discussed in each segment.",
            ParagraphStyle("warn", parent=body_s,
                           backColor=colors.HexColor("#fff7ed"),
                           borderPad=8, textColor=colors.HexColor("#92400e"))))

    story.append(sp())

    # ═══════════════════════════════════════════════════════
    # SECTION 3 — KEY MOMENTS (most important to the user)
    # ═══════════════════════════════════════════════════════
    story.append(hr())
    story.append(Paragraph("⭐ Key Moments in the Video", h2_s))
    story.append(Paragraph(
        "These are the most important moments the AI detected. "
        "Each one is included in your highlight video.",
        muted_s))
    story.append(sp(4))

    for seg in summary["highlight_map"]:
        conf  = seg["confidence"]
        color = "#16a34a" if conf >= 60 else "#0077cc" if conf >= 40 else "#9ca3af"
        row_bg = colors.HexColor("#f0fdf4") if conf >= 60 else colors.HexColor("#eff6ff")

        block = [
            [Paragraph(f"<b>#{seg['index']} &nbsp; {seg['label']}</b>",
                       ParagraphStyle("sl", parent=body_s, fontSize=10)),
             Paragraph(f"<b>{fmt(seg['start'])} → {fmt(seg['end'])}</b><br/>"
                       f"<font color='{color}'>● {conf:.0f}% confidence</font>",
                       ParagraphStyle("sr", parent=muted_s, alignment=2))]
        ]
        bt = Table(block, colWidths=[11*cm, 5*cm])
        bt.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (-1,-1), row_bg),
            ("GRID",          (0,0), (-1,-1), 0.5, colors.HexColor("#e2e8f0")),
            ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
            ("TOPPADDING",    (0,0), (-1,-1), 6),
            ("BOTTOMPADDING", (0,0), (-1,-1), 6),
            ("LEFTPADDING",   (0,0), (-1,-1), 10),
        ]))
        story.append(bt)
        story.append(sp(2))

    # ═══════════════════════════════════════════════════════
    # SECTION 4 — SPOKEN KEY POINTS (from transcript)
    # ═══════════════════════════════════════════════════════
    if summary["key_sentences"]:
        story.append(hr())
        story.append(Paragraph("💬 Important Things Said in This Video", h2_s))
        story.append(Paragraph(
            "These sentences were spoken at key moments and matched important keywords:",
            muted_s))
        story.append(sp(4))

        for item in summary["key_sentences"]:
            story.append(Paragraph(
                f'<font color="#6b7180">[{fmt(item["time"])}]</font> '
                f'"{item["text"]}"',
                quote_s))
            story.append(sp(3))

    # ═══════════════════════════════════════════════════════
    # SECTION 5 — KEYWORD HITS
    # ═══════════════════════════════════════════════════════
    if summary["keyword_hits"]:
        story.append(hr())
        story.append(Paragraph("🔑 Keyword Moments", h2_s))
        story.append(Paragraph(
            "These moments were flagged because an important keyword was spoken:",
            muted_s))
        story.append(sp(4))

        kw_data = [["Time", "Keyword", "What Was Said"]]
        for hit in summary["keyword_hits"][:12]:
            txt = hit.get("text","")
            if len(txt) > 80: txt = txt[:77] + "…"
            kw_data.append([fmt(hit["time"]), hit["keyword"], txt])

        kt = Table(kw_data, colWidths=[2*cm, 3.5*cm, 10.5*cm])
        kt.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (-1,0),  DARK),
            ("TEXTCOLOR",     (0,0), (-1,0),  colors.white),
            ("FONTNAME",      (0,0), (-1,0),  "Helvetica-Bold"),
            ("FONTSIZE",      (0,0), (-1,-1), 9),
            ("ROWBACKGROUNDS",(0,1), (-1,-1), [colors.white, colors.HexColor("#fefce8")]),
            ("GRID",          (0,0), (-1,-1), 0.5, colors.HexColor("#e5e7eb")),
            ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
            ("TOPPADDING",    (0,0), (-1,-1), 4),
            ("BOTTOMPADDING", (0,0), (-1,-1), 4),
            ("LEFTPADDING",   (0,0), (-1,-1), 6),
        ]))
        story.append(kt)
        story.append(sp())

    # ═══════════════════════════════════════════════════════
    # SECTION 6 — FULL TRANSCRIPT
    # ═══════════════════════════════════════════════════════
    if summary["has_transcript"] and summary["transcript_text"]:
        story.append(hr())
        lang = summary["transcript_language"].upper() or "?"
        story.append(Paragraph(f"📝 Full Transcript (Language: {lang})", h2_s))
        story.append(Paragraph(
            "Everything spoken in the video, transcribed automatically by Whisper AI:",
            muted_s))
        story.append(sp(4))

        # Split into paragraphs for readability
        text = summary["transcript_text"]
        # Break into chunks of ~500 chars at sentence boundaries
        chunks, current = [], ""
        for sentence in text.split("."):
            current += sentence.strip() + ". "
            if len(current) > 400:
                chunks.append(current.strip())
                current = ""
        if current.strip():
            chunks.append(current.strip())

        for chunk in chunks:
            if chunk.strip():
                story.append(Paragraph(chunk,
                    ParagraphStyle("tx", parent=body_s,
                                   backColor=colors.HexColor("#f8fafc"),
                                   borderPad=6, leading=16)))
                story.append(sp(4))

    # ═══════════════════════════════════════════════════════
    # SECTION 7 — HOW TO USE YOUR HIGHLIGHT
    # ═══════════════════════════════════════════════════════
    story.append(hr())
    story.append(Paragraph("📌 How to Use Your Highlight Video", h2_s))
    tips = [
        "✅ <b>Watch the highlight first</b> to get the key ideas in under 2 minutes",
        "✅ <b>Use the timestamps</b> in the Key Moments table to jump to specific parts in the original",
        "✅ <b>Share the highlight</b> with colleagues or students who missed the full session",
        "✅ <b>Use the transcript</b> to search for specific topics mentioned in the video",
        "✅ <b>Re-process with keywords</b> to focus the highlight on specific topics you care about",
    ]
    for tip in tips:
        story.append(Paragraph(tip, body_s))

    story.append(sp(16))
    story.append(Paragraph("Generated by HILIGHT · AI Video Highlight Generator",
                            ParagraphStyle("foot", parent=muted_s,
                                           alignment=1, fontSize=8)))

    doc.build(story)
    return str(output_path)


# ── timeline chart (kept for reference) ──────────────────────────────────

def _draw_timeline_chart(timeline, segments, width=400, height=60):
    from reportlab.graphics.shapes import Drawing, Rect
    from reportlab.lib              import colors
    W, H = float(width), float(height)
    d    = Drawing(W, H)
    if not timeline: return d
    max_time  = max((t["time"]  for t in timeline), default=1)
    max_score = max((t["score"] for t in timeline), default=1)
    bar_w     = max(1.5, W / max(len(timeline), 1))
    for s, e in segments:
        d.add(Rect((s/max_time)*W, 0, ((e-s)/max_time)*W, H,
                   fillColor=colors.HexColor("#bbf7d0"), strokeColor=None))
    for t in timeline:
        x  = (t["time"]  / max_time)  * W
        h  = (t["score"] / max_score) * (H - 8)
        fc = colors.HexColor("#16a34a") if t["is_highlight"] else colors.HexColor("#93c5fd")
        d.add(Rect(x - bar_w/2, 4, bar_w, h, fillColor=fc, strokeColor=None))
    return d
