import { useCallback } from "react";
import type { PriceBounds } from "../types";
import { formatPrice } from "../utils/format";
import styles from "../styles/FilterSidebar.module.css";

interface Props {
  bounds: PriceBounds;
  min: number;
  max: number;
  onChange: (min: number, max: number) => void;
}

export function PriceRangeSlider({ bounds, min, max, onChange }: Props) {
  const range = Math.max(1, bounds.max - bounds.min);
  const step = Math.max(1, Math.round(range / 100));
  const minPercent = ((min - bounds.min) / range) * 100;
  const maxPercent = ((max - bounds.min) / range) * 100;

  const handleMin = useCallback(
    (value: number) => onChange(Math.min(value, max), max),
    [max, onChange]
  );
  const handleMax = useCallback(
    (value: number) => onChange(min, Math.max(value, min)),
    [min, onChange]
  );

  return (
    <div className={styles.range}>
      <div className={styles.rangeValues}>
        <span>{formatPrice(min)}</span>
        <span>{formatPrice(max)}</span>
      </div>

      <div className={styles.rangeTrack}>
        <div
          className={styles.rangeFill}
          style={{ left: `${minPercent}%`, right: `${100 - maxPercent}%` }}
        />
        <input
          type="range"
          className={styles.rangeInput}
          min={bounds.min}
          max={bounds.max}
          step={step}
          value={min}
          onChange={(event) => handleMin(Number(event.target.value))}
          aria-label="Минимальная цена"
        />
        <input
          type="range"
          className={styles.rangeInput}
          min={bounds.min}
          max={bounds.max}
          step={step}
          value={max}
          onChange={(event) => handleMax(Number(event.target.value))}
          aria-label="Максимальная цена"
        />
      </div>
    </div>
  );
}
