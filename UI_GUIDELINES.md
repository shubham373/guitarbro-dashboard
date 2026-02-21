# GuitarBro Dashboard - UI Style Guidelines

This document defines the standard UI patterns, colors, and components for the GuitarBro Shopify Dashboard. **All new modules must follow these guidelines** to maintain visual consistency.

---

## Color Palette

### Primary Colors
| Name | Hex | Usage |
|------|-----|-------|
| **Brand Blue** | `#528FF0` | Primary actions, highlights, links, active states |
| **Dark Text** | `#1A1A1A` | Primary text, headings, values |
| **Background** | `#F7F8FA` | Main app background |
| **Card Background** | `#FFFFFF` | All cards and containers |
| **Border** | `#E5E7EB` | Borders, dividers |

### Text Colors
| Name | Hex | Usage |
|------|-----|-------|
| **Primary Text** | `#1A1A1A` | Headings, values, important text |
| **Body Text** | `#374151` | Paragraph text, descriptions |
| **Secondary Text** | `#6B7280` | Labels, captions, meta info |
| **Tertiary Text** | `#9CA3AF` | Sublabels, hints |

### Status Colors
| Status | Background | Text | Border |
|--------|------------|------|--------|
| **Success** | `#D1FAE5` | `#065F46` | `#10B981` |
| **Warning** | `#FEF3C7` | `#92400E` | `#F59E0B` |
| **Error** | `#FEE2E2` | `#991B1B` | `#EF4444` |
| **Info** | `#F0F7FF` | `#1E40AF` | `#528FF0` |

### Sentiment Colors
| Sentiment | Color |
|-----------|-------|
| Positive | `#22C55E` (green) |
| Neutral | `#6B7280` (gray) |
| Negative | `#EF4444` (red) |

---

## Typography

### Font Sizes
| Element | Size | Weight | Color |
|---------|------|--------|-------|
| Page Title | 28px | 700 | `#1A1A1A` |
| Section Header | 18px | 600 | `#1A1A1A` |
| Metric Value | 32px | 700 | `#1A1A1A` or `#528FF0` |
| Body Text | 14px | 400 | `#374151` |
| Label | 14px | 500 | `#6B7280` |
| Caption | 13px | 400 | `#6B7280` |
| Small Text | 12px | 400 | `#9CA3AF` |

### Usage Examples
```python
# Page title
st.markdown("<p style='font-size: 28px; font-weight: 700; color: #1A1A1A;'>Page Title</p>", unsafe_allow_html=True)

# Section header
st.markdown("<p style='font-size: 18px; font-weight: 600; color: #1A1A1A; margin: 24px 0 16px 0; border-bottom: 1px solid #E5E7EB; padding-bottom: 8px;'>Section Header</p>", unsafe_allow_html=True)

# Body text
st.markdown("<p style='color: #374151;'>Body text content here</p>", unsafe_allow_html=True)

# Caption/meta
st.markdown("<span style='color: #6B7280; font-size: 13px;'>Caption text</span>", unsafe_allow_html=True)
```

---

## Components

### 1. Metric Cards

```python
def render_metric_card(value: str, label: str, sublabel: str = "", is_blue: bool = False):
    value_color = "#528FF0" if is_blue else "#1A1A1A"
    st.markdown(f"""
    <div style="background-color: #FFFFFF; border-radius: 12px; padding: 24px;
                box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08); border: 1px solid #E5E7EB;
                border-left: 4px solid {'#528FF0' if is_blue else '#9CA3AF'}; margin-bottom: 16px;">
        <p style="font-size: 32px; font-weight: 700; color: {value_color}; margin: 0;">{value}</p>
        <p style="font-size: 14px; color: #6B7280; margin-top: 8px; font-weight: 500;">{label}</p>
        <p style="font-size: 12px; color: #9CA3AF; margin-top: 4px;">{sublabel}</p>
    </div>
    """, unsafe_allow_html=True)
```

### 2. Section Headers

```python
def render_section_header(title: str):
    st.markdown(f"""
    <p style="font-size: 18px; font-weight: 600; color: #1A1A1A;
              margin: 24px 0 16px 0; padding-bottom: 8px;
              border-bottom: 1px solid #E5E7EB;">{title}</p>
    """, unsafe_allow_html=True)
```

### 3. Pills/Badges

**Dark Badge (Category):**
```python
st.markdown(f"""
<span style="background-color: #1A1A1A; color: #FFFFFF;
             padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 500;">
    {emoji} {category}
</span>
""", unsafe_allow_html=True)
```

**Status Badges:**
```python
# Success badge
st.markdown("<span style='background-color: #D1FAE5; color: #065F46; padding: 4px 8px; border-radius: 4px; font-size: 12px;'>🟢 Active</span>", unsafe_allow_html=True)

# Warning badge
st.markdown("<span style='background-color: #FEF3C7; color: #92400E; padding: 4px 8px; border-radius: 4px; font-size: 12px;'>⚠️ Warning</span>", unsafe_allow_html=True)

# Error badge
st.markdown("<span style='background-color: #FEE2E2; color: #991B1B; padding: 4px 8px; border-radius: 4px; font-size: 12px;'>🔴 Critical</span>", unsafe_allow_html=True)
```

### 4. Info/Highlight Boxes

**Blue Info Box (for comments, quotes):**
```python
st.markdown(f"""
<div style="background-color: #F0F7FF; border-left: 4px solid #528FF0;
            padding: 12px; border-radius: 4px; margin: 12px 0;">
    <span style="color: #528FF0; font-weight: 500;">💬 Label:</span><br>
    <span style="color: #1A1A1A;">{content}</span>
</div>
""", unsafe_allow_html=True)
```

**Green Success Box (for replies, positive):**
```python
st.markdown(f"""
<div style="background-color: #F0FDF4; border-left: 4px solid #22C55E;
            padding: 12px; border-radius: 4px; margin: 12px 0;">
    <span style="color: #1A1A1A;">{content}</span>
</div>
""", unsafe_allow_html=True)
```

### 5. Cards/Containers

```python
st.markdown("""
<div style="background-color: #FFFFFF; border: 1px solid #E5E7EB;
            border-radius: 12px; padding: 16px; margin: 12px 0;
            box-shadow: 0 1px 3px rgba(0,0,0,0.08);">
    <!-- Card content here -->
</div>
""", unsafe_allow_html=True)
```

### 6. Dividers

```python
# Horizontal divider
st.markdown("<hr style='margin: 16px 0; border: none; border-top: 1px solid #E5E7EB;'>", unsafe_allow_html=True)

# Thicker section divider
st.markdown("---")  # Use Streamlit's built-in
```

### 7. Tables (for dark theme tables)

```python
# For custom HTML tables with dark header
table_html = """
<div style="border-radius: 8px; overflow: hidden; border: 1px solid #E5E7EB;">
    <table style="width: 100%; border-collapse: collapse;">
        <thead>
            <tr style="background-color: #1F2937;">
                <th style="padding: 12px 8px; color: #FFFFFF; text-align: left; font-size: 12px; border-bottom: 2px solid #528FF0;">Header</th>
            </tr>
        </thead>
        <tbody>
            <tr style="background-color: #FFFFFF;">
                <td style="padding: 12px 8px; color: #1A1A1A; font-size: 13px; border-bottom: 1px solid #E5E7EB;">Content</td>
            </tr>
        </tbody>
    </table>
</div>
"""
```

---

## Spacing Standards

| Element | Value |
|---------|-------|
| Page padding | 24px |
| Section margin-top | 24px |
| Section margin-bottom | 16px |
| Card padding | 16px - 24px |
| Card margin-bottom | 16px |
| Border-radius (large) | 12px |
| Border-radius (medium) | 8px |
| Border-radius (small) | 4px |
| Border-radius (pill) | 20px |

---

## Shadow Standards

| Type | Value |
|------|-------|
| Subtle (cards) | `0 1px 3px rgba(0, 0, 0, 0.08)` |
| Prominent (floating) | `0 2px 8px rgba(0, 0, 0, 0.15)` |

---

## Emoji Usage

| Context | Emoji |
|---------|-------|
| Overview/Stats | 📊 |
| Comments | 💬 |
| Users/Commenters | 👥 |
| Posts/Ads | 📢 |
| Settings | ⚙️ |
| Logs | 📋 |
| Price | 💰 |
| Question | ❓ |
| Doubt | 🤔 |
| Positive | 😊 |
| Negative | 😞 |
| Complaint | 😤 |
| Approve | ✅ |
| Skip | ⏭️ |
| Edit | ✏️ |
| Delete | 🗑️ |
| Brand | 🎸 |

---

## CRITICAL RULES

### ❌ NEVER DO:
1. Use white text (`#FFFFFF`, `#fff`) on light backgrounds
2. Use dark backgrounds (`#1a1a2e`, `#111827`) for main content areas
3. Leave text color unspecified (inherits may be wrong)
4. Use `st.markdown("**text**")` without explicit color styling
5. Use `st.caption()` or `st.write()` without checking visibility

### ✅ ALWAYS DO:
1. Explicitly set `color: #1A1A1A` for all visible text
2. Use `unsafe_allow_html=True` with styled HTML
3. Test visibility on light background (#F7F8FA)
4. Use the color palette defined above
5. Follow the component patterns exactly

---

## Quick Reference - Copy/Paste Styles

```python
# Black text (primary)
style="color: #1A1A1A;"

# Gray text (secondary)
style="color: #6B7280;"

# Blue text (highlight/link)
style="color: #528FF0;"

# Bold heading
style="color: #1A1A1A; font-weight: 600;"

# Card container
style="background-color: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 12px; padding: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.08);"

# Dark pill badge
style="background-color: #1A1A1A; color: #FFFFFF; padding: 4px 12px; border-radius: 20px; font-size: 12px;"

# Blue info box
style="background-color: #F0F7FF; border-left: 4px solid #528FF0; padding: 12px; border-radius: 4px; color: #1A1A1A;"
```

---

## File Structure

When adding new modules:
1. Import shared UI functions from a common module (future)
2. Add module-specific CSS at the start of render function
3. Follow the nav_items pattern in app.py for navigation
4. Use consistent tab naming with emoji prefixes

---

*Last updated: February 2026*
*Maintainer: GuitarBro Team*
