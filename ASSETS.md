# Assets Documentation

This document describes the visual assets, branding, and design system used in Web Forx ControlHub.

## Brand Identity

### Product Name
- **Full Name**: Web Forx ControlHub
- **Company**: Web Forx Global Inc.
- **Tagline**: Admin, audit, and operational control for modern teams.

### Logo
- **Primary Logo**: "W" icon + "Web Forx ControlHub" text
- **Icon**: Gradient square with "W" letter
- **Colors**: Cyan gradient (#00D4FF → #0099CC)

### Typography
- **Primary Font**: Inter (Google Fonts)
- **Monospace Font**: JetBrains Mono (for code/timestamps)

### Color Palette

| Token | Hex | Usage |
|-------|-----|-------|
| `--color-primary` | `#00D4FF` | Buttons, links, accents |
| `--color-primary-dark` | `#0099CC` | Hover states, gradients |
| `--color-bg-primary` | `#0A0F1C` | Main background |
| `--color-bg-secondary` | `#111827` | Cards, sidebar |
| `--color-bg-tertiary` | `#1F2937` | Inputs, hover states |
| `--color-success` | `#10B981` | Active status, success |
| `--color-warning` | `#F59E0B` | Admin role, warnings |
| `--color-error` | `#EF4444` | Superadmin role, errors |
| `--color-info` | `#3B82F6` | Viewer role, info |

## Design System

### CSS Variables Location
- `/admin-ui/src/styles/variables.css` - All design tokens
- `/admin-ui/src/styles/base.css` - Base styles and resets

### Spacing Scale
```
xs: 0.25rem (4px)
sm: 0.5rem (8px)
md: 1rem (16px)
lg: 1.5rem (24px)
xl: 2rem (32px)
2xl: 3rem (48px)
```

### Border Radius
```
sm: 0.25rem
md: 0.5rem
lg: 0.75rem
xl: 1rem
full: 9999px
```

## UI Components

### Location
All reusable components are in `/admin-ui/src/components/ui/`

### Available Components

| Component | File | Description |
|-----------|------|-------------|
| Button | `Button.jsx` | Primary, secondary, danger, ghost, outline variants |
| Input | `Input.jsx` | Text input, Select, TextArea with labels and errors |
| Card | `Card.jsx` | Container with Header, Body, Footer sections |
| Badge | `Badge.jsx` | RoleBadge, StatusBadge for tags |
| Modal | `Modal.jsx` | Dialog with ConfirmModal variant |
| Toast | `Toast.jsx` | Notifications with ToastProvider |
| Spinner | `Spinner.jsx` | Loading indicators, PageLoader, TableLoader |
| Pagination | `Pagination.jsx` | Page navigation controls |

### Usage
```jsx
import Button from '../components/ui/Button';
import Card, { CardHeader, CardBody } from '../components/ui/Card';
import { useToast } from '../components/ui/Toast';

function MyComponent() {
  const toast = useToast();
  
  return (
    <Card>
      <CardHeader title="Title" subtitle="Description" />
      <CardBody>
        <Button onClick={() => toast.success('Done!')}>
          Click Me
        </Button>
      </CardBody>
    </Card>
  );
}
```

## Layout Structure

### Sidebar
- Width: 260px (fixed)
- Sections: Overview, Management, System
- Header: "Web Forx ControlHub" with "by Web Forx Global Inc." subtitle
- Footer: Web Forx Global Inc. link

### Top Navigation
- Height: 64px (fixed)
- Left: Breadcrumbs
- Right: Environment badge, User dropdown

### Main Content
- Padding: 32px
- Footer: Copyright + links

## Role Badge Colors

| Role | Badge Color |
|------|-------------|
| superadmin | Error (red) |
| admin | Warning (amber) |
| viewer | Info (blue) |
| user | Default (gray) |

## Status Badge

| Status | Color |
|--------|-------|
| Active | Success (green) |
| Disabled | Error (red) |

## Recommended Logo Assets

If creating custom logo assets, use these specifications:

| Asset | Size | Format |
|-------|------|--------|
| Favicon | 32x32 | ICO/PNG |
| Logo Icon | 40x40 | SVG |
| Logo Full | 200x40 | SVG |
| OG Image | 1200x630 | PNG |

## Icon Usage

Currently using emoji icons for simplicity:
- 📊 Dashboard
- 👥 Users
- 📁 Uploads
- ⚙️ Jobs/Settings
- 📋 Audit Logs
- 🔧 Settings
- 🔑 Login
- 🚪 Logout

For production, consider replacing with:
- Heroicons
- Lucide Icons
- Phosphor Icons

## Environment Badge

| Environment | Color |
|-------------|-------|
| DEV | Info (blue) |
| STAGING | Warning (amber) |
| PROD | Error (red) |
