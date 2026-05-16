export default function PageHeader({
  eyebrow = null,
  title,
  subtitle,
  children,
}) {
  return (
    <div className="mb-6 flex items-center justify-between">
      <div>
        {eyebrow ? (
          <div className="mb-1 text-xs font-medium uppercase tracking-wide text-sre-text-muted">
            {eyebrow}
          </div>
        ) : null}
        <h1 className="text-3xl font-bold text-sre-text mb-2">{title}</h1>
        <p className="text-sre-text-muted">{subtitle}</p>
      </div>
      {children && <div className="flex items-center gap-2">{children}</div>}
    </div>
  );
}
