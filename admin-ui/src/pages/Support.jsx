import Card, { CardBody } from "../components/ui/Card";
import Markdown from "../components/ui/Markdown";
import "./DocPage.css";

const supportContent = `# Support & Troubleshooting

Welcome to Web Forx Admin support. This guide will help you resolve common issues and get assistance when needed.

## Getting Help

### Self-Service Resources

1. Check this troubleshooting guide first
2. Review the Documentation section below
3. Check system status on the Dashboard

### Contact Support

**Email:** support@webforxtech.com
**Website:** https://www.webforxtech.com/
**Hours:** Monday - Friday, 9am - 6pm EST

## What to Include in Support Requests

When contacting support, please provide:

1. Your email/username
2. Browser and version (e.g., Chrome 120)
3. Operating system (e.g., Windows 11, macOS 14)
4. Steps to reproduce the issue
5. Error messages (exact text or screenshot)
6. Timestamp when the issue occurred

## Environment Information

To find your environment details:

1. Go to **Settings** page
2. Look under "System Information" section
3. Note the Environment and API Endpoint values

## Common Errors & Solutions

### Login Issues

| Error | Cause | Solution |
|-------|-------|----------|
| Invalid email or password | Wrong credentials | Check email/password; contact admin for reset |
| Account is disabled | Admin disabled account | Contact your administrator |
| Unable to reach server | Network/API issue | Check internet connection; try again later |

### Permission Errors

| Error | Cause | Solution |
|-------|-------|----------|
| Access denied | Insufficient role | Contact admin for role upgrade |
| Cannot modify your own account | Self-edit restriction | Ask another admin to make changes |
| Cannot manage higher roles | Role hierarchy | Only higher roles can manage lower roles |

### Session Issues

| Error | Cause | Solution |
|-------|-------|----------|
| Automatic logout | Token expired | Log in again |
| 401 Unauthorized | Invalid/expired token | Clear browser data and log in again |

### Data Loading Issues

| Error | Cause | Solution |
|-------|-------|----------|
| Failed to load... | API error | Refresh page; check network |
| Empty tables | No data or filter too strict | Clear filters; verify data exists |
| Slow loading | Large dataset | Use pagination; add filters |

## Troubleshooting Steps

### Step 1: Refresh & Retry
- Press Ctrl+F5 (Windows) or Cmd+Shift+R (Mac) to hard refresh
- Wait 30 seconds and try again

### Step 2: Clear Browser Data
1. Open browser settings
2. Clear cookies and cache for this site
3. Log in again

### Step 3: Try Different Browser
- Test in Chrome, Firefox, or Safari
- Disable browser extensions temporarily

### Step 4: Check Network
- Verify internet connection
- Check if API endpoint is accessible
- Look for firewall/VPN issues

### Step 5: Check Console
1. Press F12 to open Developer Tools
2. Go to "Console" tab
3. Look for red error messages
4. Include these in support requests

## Role Permissions

| Role | Capabilities |
|------|--------------|
| **User** | View own profile |
| **Viewer** | Read-only access to admin panels |
| **Admin** | Manage users (except superadmins) |
| **Superadmin** | Full system access |

## Escalation Path

1. **Level 1:** Self-service troubleshooting (this guide)
2. **Level 2:** Contact your organization's admin
3. **Level 3:** Email support@webforxtech.com
4. **Level 4:** Request escalation to engineering team

## System Requirements

### Supported Browsers
- Chrome 90+
- Firefox 90+
- Safari 14+
- Edge 90+

### Network Requirements
- Stable internet connection
- Access to API endpoint (port 9000 by default)

## Feedback

We value your feedback! Send suggestions to:
**feedback@webforxtech.com**
`;

export default function Support() {
  return (
    <div className="doc-page">
      <div className="page-header">
        <h1 className="page-title">Support</h1>
        <p className="page-subtitle">Get help and troubleshoot common issues</p>
      </div>

      <Card>
        <CardBody>
          <Markdown content={supportContent} />
        </CardBody>
      </Card>
    </div>
  );
}
