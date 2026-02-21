# Styling Guide - GuitarBro Dashboard

## How to Apply Styles (For Developers)

**EVERY module MUST use the shared styles module:**

```python
from shared_styles import inject_custom_css

def render_your_module():
    inject_custom_css()  # Call this FIRST
    # ... rest of code
```

The shared styles are defined in `src/shared_styles.py`. **Never write inline CSS.**

---

## Core Principle: Text Readability

**Text is either BLACK or WHITE. Never use gray text or low-contrast combinations.**

---

## Text Color Rules

| Background Type | Text Color | Hex Code |
|-----------------|------------|----------|
| No pill/overlay (plain background) | **BLACK** | `#000000` |
| Blue pill/badge background | **BLACK** | `#000000` |
| Dark/Black/Gray pill background | **WHITE** | `#FFFFFF` |

---

## Color Palette

### Blues (for pills, borders, highlights)
| Name | Hex | Usage |
|------|-----|-------|
| Light Blue | `#DBEAFE` | Pill backgrounds, metric cards, tabs |
| Medium Blue | `#93C5FD` | Borders, dividers |
| Dark Blue | `#3B82F6` | Accents, links |
| Very Light Blue | `#EFF6FF` | Subtle backgrounds |

### Grays (for dark pills)
| Name | Hex | Usage |
|------|-----|-------|
| Dark Gray | `#374151` | Dark pill backgrounds (use WHITE text) |
| Darker Gray | `#1F2937` | File badges, dark elements (use WHITE text) |

### Status Colors
| Status | Background | Text |
|--------|------------|------|
| Success | `#D1FAE5` | `#000000` (BLACK) |
| Error | `#FEE2E2` | `#000000` (BLACK) |
| Warning | `#FEF3C7` | `#000000` (BLACK) |
| Info | `#DBEAFE` | `#000000` (BLACK) |

---

## Component Styling

### 1. Normal Text
```css
color: #000000;
/* No background, just black text */
```

### 2. Blue Pill (Button, Badge, Tab)
```css
background-color: #DBEAFE;
color: #000000;
border: 1px solid #93C5FD;
border-radius: 20px; /* or 8px for less rounded */
```

### 3. Dark Pill (File Upload Zone, Dark Badge)
```css
background-color: #374151;
color: #FFFFFF;
border-radius: 8px;
```

### 4. Metric Cards
```css
background-color: #DBEAFE;
color: #000000;
border: 1px solid #93C5FD;
border-radius: 12px;
padding: 16px;
```

### 5. File Uploader
```css
/* Outer container - Blue border */
background-color: #EFF6FF;
border: 2px dashed #3B82F6;
border-radius: 12px;

/* Inner drop zone - Dark gray, WHITE text */
section {
    background-color: #374151;
    color: #FFFFFF;
}

/* Label outside - BLACK text */
label {
    color: #000000;
}
```

### 6. Tabs
```css
/* Tab container */
background-color: #EFF6FF;
border-radius: 8px;

/* Selected tab */
background-color: #DBEAFE;
color: #000000;
font-weight: 600;

/* Unselected tab */
background-color: transparent;
color: #000000;
```

### 7. Data Tables
```css
/* Header row */
th {
    background-color: #DBEAFE;
    color: #000000;
    font-weight: 600;
}

/* Data cells */
td {
    background-color: #FFFFFF;
    color: #000000;
}

/* Border */
border: 1px solid #93C5FD;
```

### 8. Input Fields
```css
/* Label */
label {
    color: #000000;
    font-weight: 500;
}

/* Input box */
input, select {
    background-color: #FFFFFF;
    color: #000000;
    border: 1px solid #93C5FD;
}
```

### 9. Alerts/Info Boxes
```css
/* Blue info box */
background-color: #DBEAFE;
color: #000000;
border: 1px solid #93C5FD;

/* Always BLACK text in alerts */
```

---

## Quick Reference

```
┌─────────────────────────────────────────────┐
│  STYLING DECISION TREE                      │
├─────────────────────────────────────────────┤
│                                             │
│  Is there a pill/background?                │
│  ├── NO  → Use BLACK text (#000000)         │
│  └── YES → What color is the background?    │
│            ├── Blue/Light → BLACK text      │
│            └── Dark/Gray  → WHITE text      │
│                                             │
└─────────────────────────────────────────────┘
```

---

## File Uploader Example

```
┌──────────────────────────────────────────────┐  ← Blue dashed border
│  Upload Shopify Orders CSV  (BLACK text)     │  ← Label (no pill)
│                                              │
│  ┌────────────────────────────────────────┐  │
│  │  Drag and drop file here  (WHITE)      │  │  ← Dark gray pill
│  │  Limit 200 MB per file    (WHITE)      │  │  ← WHITE text
│  └────────────────────────────────────────┘  │
│                                              │
└──────────────────────────────────────────────┘
```

---

## DO NOT

❌ Never use gray text on white background
❌ Never use white text on white/light background
❌ Never use black text on black/dark background
❌ Never use low-contrast color combinations

## ALWAYS

✅ Test readability by squinting - if you can't read it, fix it
✅ Use BLACK for normal text
✅ Use WHITE only on dark backgrounds
✅ Maintain consistent styling across all modules

---

*Last Updated: 2026-02-18*
