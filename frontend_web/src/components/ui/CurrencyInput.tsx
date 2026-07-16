import { forwardRef, type ChangeEvent, type FocusEvent, type InputHTMLAttributes } from "react";
import { formatCurrencyInputBR, sanitizeBrazilianDecimalInput } from "../../utils/formatters";

type CurrencyInputProps = Omit<InputHTMLAttributes<HTMLInputElement>, "type" | "inputMode"> & {
  label: string;
  error?: string;
};

export const CurrencyInput = forwardRef<HTMLInputElement, CurrencyInputProps>(function CurrencyInput(
  { label, error, id, onChange, onBlur, placeholder = "R$ 0,00", ...props },
  ref,
) {
  const inputId = id ?? props.name ?? label;

  function handleChange(event: ChangeEvent<HTMLInputElement>) {
    const sanitized = sanitizeBrazilianDecimalInput(event.target.value);
    if (sanitized !== event.target.value) {
      event.target.value = sanitized;
    }
    onChange?.(event);
  }

  function handleBlur(event: FocusEvent<HTMLInputElement>) {
    const formatted = formatCurrencyInputBR(event.target.value);
    if (formatted) {
      event.target.value = formatted;
      onChange?.(event as unknown as ChangeEvent<HTMLInputElement>);
    }
    onBlur?.(event);
  }

  return (
    <label className="field" htmlFor={inputId}>
      <span>{label}</span>
      <input
        id={inputId}
        ref={ref}
        type="text"
        inputMode="decimal"
        placeholder={placeholder}
        {...props}
        aria-invalid={Boolean(error)}
        aria-describedby={error ? `${inputId}-error` : undefined}
        onChange={handleChange}
        onBlur={handleBlur}
      />
      {error ? <small id={`${inputId}-error`}>{error}</small> : null}
    </label>
  );
});
