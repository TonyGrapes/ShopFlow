// frontend/src/types/category.ts
/**
 * Типы, синхронные с app/schemas/category.py.
 */
export interface Category {
  id: number;
  category_name: string;
  path: string;
  parent_id: number | null;
}

export interface CategoryTree {
  id: number;
  category_name: string;
  path: string;
  children: CategoryTree[];
}
