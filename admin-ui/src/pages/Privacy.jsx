import Card, { CardBody } from "../components/ui/Card";
import Markdown from "../components/ui/Markdown";
import "./DocPage.css";

const privacyContent = `# Privacy Policy

**Last Updated:** January 2026

Web Forx Admin ("the Application") is committed to protecting your privacy. This policy explains how we collect, use, and safeguard your information.

## Information We Collect

### Account Information
- Email address (used for authentication)
- Password (stored securely using bcrypt hashing)
- Role assignment (for access control)

### Usage Data
- Login timestamps and IP addresses
- Actions performed within the application (audit logs)
- Browser user agent information

### Technical Data
- Session tokens (JWT)
- Browser cookies for session management

## How We Use Your Information

We use collected information to:

1. **Authenticate** your identity and manage access
2. **Authorize** actions based on your role permissions
3. **Audit** system activity for security and compliance
4. **Improve** application performance and user experience

## Data Storage & Security

### Storage
- All data is stored in PostgreSQL databases
- Passwords are hashed using bcrypt (never stored in plain text)
- JWT tokens expire after configured timeout

### Security Measures
- HTTPS encryption for all data transmission
- Role-based access control (RBAC)
- Audit logging of sensitive operations
- Session invalidation on logout

## Data Retention

| Data Type | Retention Period |
|-----------|------------------|
| User accounts | Until deleted by admin |
| Audit logs | 90 days (configurable) |
| Session tokens | Until logout or expiration |

## Your Rights

You have the right to:

- **Access** your personal data
- **Correct** inaccurate information
- **Delete** your account (contact admin)
- **Export** your data upon request

## Cookies & Local Storage

We use:

| Type | Purpose | Duration |
|------|---------|----------|
| JWT Token | Authentication | Session |
| User Data | Display preferences | Session |

No third-party tracking cookies are used.

## Contact

For privacy concerns, contact your system administrator or:

**Web Forx Technologies**
Email: privacy@webforxtech.com
Website: https://www.webforxtech.com/

## Changes to This Policy

We may update this policy periodically. Significant changes will be communicated through the application.
`;

export default function Privacy() {
  return (
    <div className="doc-page">
      <div className="page-header">
        <h1 className="page-title">Privacy Policy</h1>
        <p className="page-subtitle">How we collect, use, and protect your data</p>
      </div>

      <Card>
        <CardBody>
          <Markdown content={privacyContent} />
        </CardBody>
      </Card>
    </div>
  );
}
