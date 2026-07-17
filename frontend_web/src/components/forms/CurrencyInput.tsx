import { forwardRef, useEffect, useState, type ClipboardEvent, type ChangeEvent, type InputHTMLAttributes } from "react";
import {
  currencyDisplayToDecimal,
  decimalToCurrencyDisplay,
  digitsToCurrencyDisplay,
} from "../../utils/formatters";

type CurrencyInputProps = Omit<InputHTMLAttributes<HTMLInputElement>, "type" | "inputMode"> & {
  label: string;
  error?: string;
  allowNegative?: boolean;
};

export const CurrencyInput = forwardRef<HTMLInputElement, CurrencyInputProps>(function CurrencyInput(
  { label, error, id, onChange, onPaste, value, defaultValue, allowNegative = false, ...props },
  ref,
) {
  const inputId = id ?? props.name ?? label;
  const isControlled = value !== undefined;
  const [internalValue, setInternalValue] = useState(() => decimalToCurrencyDisplay(inputValueToString(defaultValue ?? value)));
  const displayedValue = isControlled ? decimalToCurrencyDisplay(inputValueToString(value)) : internalValue;

  useEffect(() => {
    if (isControlled) {
      setInternalValue(decimalToCurrencyDisplay(inputValueToString(value)));
    }
  }, [isControlled, value]);

  function emitValue(nextValue: string, event: ChangeEvent<HTMLInputElement>) {
    if (!isControlled) {
      setInternalValue(nextValue);
    }
    event.target.value = nextValue;
    onChange?.(event);
    window.requestAnimationFrame(() => {
      event.target.setSelectionRange(nextValue.length, nextValue.length);
    });
  }

  function handleChange(event: ChangeEvent<HTMLInputElement>) {
    const raw = event.target.value;
    const negative = allowNegative && raw.trim().startsWith("-");
    const digits = raw.replace(/\D/g, "");
    const nextValue = digitsToCurrencyDisplay(digits, negative);
    emitValue(nextValue, event);
  }

  function handlePaste(event: ClipboardEvent<HTMLInputElement>) {
    event.preventDefault();
    const pasted = event.clipboardData.getData("text");
    const decimal = currencyDisplayToDecimal(pasted, { allowNegative });
    const nextValue = decimalToCurrencyDisplay(decimal);
    const changeEvent = {
      ...event,
      target: event.currentTarget,
      currentTarget: event.currentTarget,
    } as unknown as ChangeEvent<HTMLInputElement>;
    emitValue(nextValue, changeEvent);
    onPaste?.(event);
  }

  return (
    <label className="field" htmlFor={inputId}>
      <span>{label}</span>
      <input
        id={inputId}
        ref={ref}
        type="text"
        inputMode="numeric"
        value={displayedValue}
        {...props}
        aria-invalid={Boolean(error)}
        aria-describedby={error ? `${inputId}-error` : undefined}
        onChange={handleChange}
        onPaste={handlePaste}
      />
      {error ? <small id={`${inputId}-error`}>{error}</small> : null}
    </label>
  );
});

function inputValueToString(value: string | number | readonly string[] | undefined) {
  if (Array.isArray(value)) return value[0] ?? "0";
  return value ?? "0";
}
