// frontend/src/pages/ProductPage.tsx
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { fetchProduct } from "../api/products";
import { ApiError } from "../api/client";
import { LoadingState } from "../components/LoadingState";
import { ErrorState } from "../components/ErrorState";
import type { ProductResponse } from "../types/product";

export function ProductPage() {
  const { id } = useParams<{ id: string }>();
  const productId = Number(id);

  const [product, setProduct] = useState<ProductResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeImage, setActiveImage] = useState(0);

  useEffect(() => {
    if (!Number.isFinite(productId)) {
      setError("Некорректный ID товара");
      return;
    }

    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const result = await fetchProduct(productId);
        if (!cancelled) {
          setProduct(result);
          setActiveImage(0);
        }
      } catch (err) {
        if (cancelled) return;
        if (err instanceof ApiError) {
          if (err.status === 404) setError("Товар не найден");
          else setError(`${err.status}: ${err.detail}`);
        } else if (err instanceof Error) {
          setError(err.message);
        } else {
          setError("Неизвестная ошибка");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => { cancelled = true; };
  }, [productId]);

  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} />;
  if (!product) return null;

  const images = product.images ?? [];

  return (
    <div className="product-page">
      <Link to="/">← Назад в каталог</Link>

      <h1>{product.name}</h1>

      <div className="product-page__content">
        <div className="product-page__gallery">
          {images.length > 0 ? (
            <>
              <img
                className="product-page__main-image"
                src={images[activeImage]?.url}
                alt={product.name}
              />
              {images.length > 1 && (
                <div className="product-page__thumbs">
                  {images.map((img, i) => (
                    <button
                      key={img.id}
                      className={i === activeImage ? "active" : ""}
                      onClick={() => setActiveImage(i)}
                    >
                      <img src={img.url} alt={`${product.name} ${i + 1}`} />
                    </button>
                  ))}
                </div>
              )}
            </>
          ) : (
            <div className="product-page__no-image">Нет изображений</div>
          )}
        </div>

        <div className="product-page__info">
          <p className="product-page__cost">{product.cost} ₽</p>
          <p className="product-page__status">
            {formatStatus(product.status)}
          </p>
          {product.category && (
            <p className="product-page__category">
              Категория: {product.category.category_name}
            </p>
          )}
          <p className="product-page__description">{product.description}</p>
        </div>
      </div>
    </div>
  );
}

function formatStatus(status: string): string {
  switch (status) {
    case "available": return "В наличии";
    case "out_of_stock": return "Нет в наличии";
    case "discontinued": return "Снят с производства";
    default: return status;
  }
}