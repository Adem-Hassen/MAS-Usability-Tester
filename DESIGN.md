# Design system — Nexus Accessibility Evaluator

This document serves as the single source of truth for the visual and functional design of the Nexus Accessibility Evaluator platform.

## Colors

The palette is optimized for high-stakes technical environments, prioritizing clarity, precision, and long-duration focus.

### Core Palette (Dark Mode)
- **Background**: `#13121B` (Deep Obsidian base canvas)
- **Primary**: `#C4C0FF` (Electric Indigo - Primary actions and active intent)
- **Secondary**: `#54DBC2` (Neon Emerald - Profit, Trust, and Success states)
- **Tertiary**: `#FFB3AF` (Coral/Cyber Amber - High-priority attention)
- **Error**: `#FFB4AB` (Rose - Critical failures and accessibility violations)
- **Surface**: `#13121B` (Standard card/panel background)
- **Surface Variant**: `#35343E` (Elevated surfaces, hover states)
- **Outline**: `#918FA1` (Default borders and dividers)
- **Outline Variant**: `#464555` (Subtle "Ghost" borders, 15% opacity recommended)

### Semantic Mapping
- **On Primary**: `#2000A4`
- **Primary Container**: `#8781FF`
- **On Primary Container**: `#1B0091`
- **Success Badge**: bg `#00AF97`, text `#003824`
- **Error Badge**: bg `#93000A`, text `#FFDAD6`
- **Running Status**: Electric Indigo glow/pulse
- **Terminal Logs**:
  - `[PASS]`: Teal
  - `[FAIL]`: Coral

## Typography

The system employs a three-family strategy to balance character and utility.

| Category | Font Family | Size | Weight | Line Height | Letter Spacing |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **H1 (Titles)** | Syne | 32px | 700 | 1.2 | -0.02em |
| **H2 (Headers)** | Syne | 24px | 600 | 1.3 | -0.01em |
| **H3 (Sub-headers)** | Syne | 18px | 600 | 1.4 | 0 |
| **Body MD** | DM Sans | 14px | 400 | 1.6 | 0 |
| **Body SM** | DM Sans | 12px | 400 | 1.5 | 0 |
| **Mono UI** | JetBrains Mono | 13px | 500 | 1.4 | 0 |
| **Mono Code** | JetBrains Mono | 12px | 400 | 1.8 | 0 |

- **Global Health Scores**: Use H1 (32px) or larger for massive impact.
- **Section Headers**: Use H2 or H3.
- **Technical Logs**: Use Mono Code for character-perfect alignment.

## Spacing

The layout is built on a strict **4px grid** following a 4/8/12/16/24 progression.

- **Base Unit**: 4px
- **Sidebar Width**: 260px (Fixed)
- **Container Margin**: 24px
- **Gutter**: 16px
- **Component Padding (X)**: 12px
- **Component Padding (Y)**: 8px
- **Metric Card Gap**: 24px

## Components

### 1. Buttons
- **Shape**: 0px border-radius (Strictly Geometric/Sharp).
- **Primary**: Indigo Gradient (#8781FF to #C4C0FF) at 135°.
- **Interactions**: On hover, apply a 15px blur "bloom" effect using the primary color.
- **Micro-animation**: 2px Y-axis lift on hover (200ms ease-out).

### 2. Cards & Containers
- **Shape**: 0px border-radius.
- **Border**: 1px `#464555` (Ghost Border).
- **Depth**: Tonal Tiering (Level 0: #0E0F11, Level 1: #161820, Level 2: #1E2028).
- **Glassmorphism**: 70% opacity with 16px backdrop-blur for floating panels.

### 3. Badges & Indicators
- **Shape**: Pill-shaped (the only exception to the sharp-corner rule).
- **Status Dot**: 6px leading dot. Pulses (0.4 to 1.0 opacity) when status is "Running."
- **Avatars**: 28px circles.

### 4. Specialized UI Elements
- **Dashed Upload Zone**: Background #161820 with a 1px dashed border (#2A2D3E).
- **Vertical Pipeline Stepper**: 1px vertical line with square nodes. Solid Teal (Complete), Indigo Glow (Active), Hollow (Pending).
- **Metric Cards**: Top-border accent reflecting health (Teal/Amber/Coral).
- **Terminal Log Panel**: Background #0E0F11, Mono Code font, high information density.

## Dark Mode

Nexus is "Dark First." The system uses **Tonal Tiering** instead of standard grey-scales.

- **Background (Base Layer)**: `#0E0F11`
- **Surface (Primary Panels)**: `#161820`
- **Elevated (Modals/Popovers)**: `#1E2028`
- **Text Selection**: Indigo tint with high contrast.

## Animation & Transitions

- **Global Transition**: 200ms `cubic-bezier(0.4, 0, 0.2, 1)`.
- **Hover States**: Subtle Y-axis translation and tonal shift.
- **Running States**: Periodic radial pulse for active background processes.
- **Connectors**: 90-degree angular paths (no curved lines permitted).
