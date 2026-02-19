import { useState, useRef, useEffect } from 'react';
import './Dropdown.css';

export default function Dropdown({ trigger, children, align = 'right' }) {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef(null);

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  useEffect(() => {
    const handleEscape = (e) => {
      if (e.key === 'Escape') {
        setIsOpen(false);
      }
    };
    window.addEventListener('keydown', handleEscape);
    return () => window.removeEventListener('keydown', handleEscape);
  }, []);

  return (
    <div className="dropdown" ref={dropdownRef}>
      <div className="dropdown-trigger" onClick={() => setIsOpen(!isOpen)}>
        {trigger}
      </div>
      {isOpen && (
        <div className={`dropdown-menu dropdown-${align}`}>
          <div onClick={() => setIsOpen(false)}>
            {children}
          </div>
        </div>
      )}
    </div>
  );
}

export function DropdownItem({ icon, children, onClick, danger = false, disabled = false }) {
  return (
    <button
      className={`dropdown-item ${danger ? 'dropdown-item-danger' : ''} ${disabled ? 'dropdown-item-disabled' : ''}`}
      onClick={disabled ? undefined : onClick}
      disabled={disabled}
    >
      {icon && <span className="dropdown-item-icon">{icon}</span>}
      <span>{children}</span>
    </button>
  );
}

export function DropdownDivider() {
  return <div className="dropdown-divider" />;
}
