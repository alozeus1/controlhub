import './Pagination.css';
import Button from './Button';

export default function Pagination({
  page,
  pages,
  total,
  pageSize,
  onPageChange,
  className = ''
}) {
  if (pages <= 1) return null;

  const start = (page - 1) * pageSize + 1;
  const end = Math.min(page * pageSize, total);

  return (
    <div className={`pagination ${className}`}>
      <span className="pagination-info">
        Showing {start}-{end} of {total}
      </span>
      <div className="pagination-controls">
        <Button
          variant="ghost"
          size="sm"
          disabled={page === 1}
          onClick={() => onPageChange(1)}
          aria-label="First page"
        >
          ««
        </Button>
        <Button
          variant="ghost"
          size="sm"
          disabled={page === 1}
          onClick={() => onPageChange(page - 1)}
          aria-label="Previous page"
        >
          ‹
        </Button>
        <span className="pagination-current">
          Page {page} of {pages}
        </span>
        <Button
          variant="ghost"
          size="sm"
          disabled={page === pages}
          onClick={() => onPageChange(page + 1)}
          aria-label="Next page"
        >
          ›
        </Button>
        <Button
          variant="ghost"
          size="sm"
          disabled={page === pages}
          onClick={() => onPageChange(pages)}
          aria-label="Last page"
        >
          »»
        </Button>
      </div>
    </div>
  );
}
