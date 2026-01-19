import './Spinner.css';

export default function Spinner({ size = 'md', className = '' }) {
  return (
    <div className={`spinner spinner-${size} ${className}`} role="status">
      <span className="sr-only">Loading...</span>
    </div>
  );
}

export function PageLoader({ message = 'Loading...' }) {
  return (
    <div className="page-loader">
      <Spinner size="lg" />
      <p className="page-loader-text">{message}</p>
    </div>
  );
}

export function TableLoader({ rows = 5, cols = 4 }) {
  return (
    <div className="table-loader">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="table-loader-row">
          {Array.from({ length: cols }).map((_, j) => (
            <div key={j} className="table-loader-cell skeleton" />
          ))}
        </div>
      ))}
    </div>
  );
}
