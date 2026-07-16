import type { SelectHTMLAttributes } from "react";

type SelectProps = SelectHTMLAttributes<HTMLSelectElement> & {
  label: string;
  error?: string;
};

export function Select({ label, error, id, children, ...props }: SelectProps) {
  const selectId = id ?? props.name ?? label;
  return (
    <label className="field" htmlFor={selectId}>
      <span>{label}</span>
      <select id={selectId} aria-invalid={Boolean(error)} {...props}>
        {children}
      </select>
      {error ? <small>{error}</small> : null}
    </label>
  );
}
