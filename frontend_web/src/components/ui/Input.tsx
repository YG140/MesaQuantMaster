import type { InputHTMLAttributes } from "react";

type InputProps = InputHTMLAttributes<HTMLInputElement> & {
  label: string;
  error?: string;
};

export function Input({ label, error, id, ...props }: InputProps) {
  const inputId = id ?? props.name ?? label;
  return (
    <label className="field" htmlFor={inputId}>
      <span>{label}</span>
      <input id={inputId} aria-invalid={Boolean(error)} aria-describedby={error ? `${inputId}-error` : undefined} {...props} />
      {error ? <small id={`${inputId}-error`}>{error}</small> : null}
    </label>
  );
}
