import { forwardRef, type ChangeEvent, type InputHTMLAttributes } from "react";
import { sanitizeBrazilianDecimalInput } from "../../utils/formatters";

type DecimalInputProps = Omit<InputHTMLAttributes<HTMLInputElement>, "type" | "inputMode"> & {
  label: string;
  error?: string;
};

export const DecimalInput = forwardRef<HTMLInputElement, DecimalInputProps>(function DecimalInput(
  { label, error, id, onChange, ...props },
  ref,
) {
  const inputId = id ?? props.name ?? label;

  function handleChange(event: ChangeEvent<HTMLInputElement>) {
    event.target.value = sanitizeBrazilianDecimalInput(event.target.value);
    onChange?.(event);
  }

  return (
    <label className="field" htmlFor={inputId}>
      <span>{label}</span>
      <input
        id={inputId}
        ref={ref}
        type="text"
        inputMode="decimal"
        {...props}
        aria-invalid={Boolean(error)}
        aria-describedby={error ? `${inputId}-error` : undefined}
        onChange={handleChange}
      />
      {error ? <small id={`${inputId}-error`}>{error}</small> : null}
    </label>
  );
});
