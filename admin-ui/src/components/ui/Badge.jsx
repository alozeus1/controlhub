import './Badge.css';

export default function Badge({
  children,
  variant = 'default',
  size = 'md',
  className = ''
}) {
  return (
    <span className={`badge badge-${variant} badge-${size} ${className}`}>
      {children}
    </span>
  );
}

export function RoleBadge({ role }) {
  const variants = {
    superadmin: 'error',
    admin: 'warning',
    viewer: 'info',
    user: 'default'
  };
  return <Badge variant={variants[role] || 'default'}>{role}</Badge>;
}

export function StatusBadge({ active }) {
  return (
    <Badge variant={active ? 'success' : 'error'}>
      {active ? 'Active' : 'Disabled'}
    </Badge>
  );
}
