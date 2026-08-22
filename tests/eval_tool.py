import logging
from logging import Logger

logger: Logger = logging.getLogger(__name__)


import pandas as pd


def equal_dataframes(df1: pd.DataFrame, df2: pd.DataFrame) -> bool:
    """Compara si dos DataFrames tienen los mismos valores y cantidad de columnas,

    ignorando nombres de columnas, tipos exactos y orden de filas.
    """
    # 1. Verificar dimensiones
    if df1.shape[1] != df2.shape[1]:
        logger.debug("Los dataframes de comparacion tienen cantidades de columnas diferentes")
        return False

    df1_norm = df1.copy()
    df2_norm = df2.copy()

    # 2. Normalizar nombres de columnas a índices
    df1_norm.columns = range(df1_norm.shape[1])
    df2_norm.columns = range(df2_norm.shape[1])

    # 3. Limpieza y conversión segura por columna
    for col in df1_norm.columns:
        # Para el DataFrame 1
        try:
            df1_norm[col] = pd.to_numeric(df1_norm[col])
        except (ValueError, TypeError):
            df1_norm[col] = (
                df1_norm[col].astype(str).str.strip().str.replace(r"\s+", " ", regex=True)
            )

        # Para el DataFrame 2
        try:
            df2_norm[col] = pd.to_numeric(df2_norm[col])
        except (ValueError, TypeError):
            df2_norm[col] = (
                df2_norm[col].astype(str).str.strip().str.replace(r"\s+", " ", regex=True)
            )

    # 4. Ordenar filas según todas las columnas
    cols = list(df1_norm.columns)
    df1_sorted = df1_norm.sort_values(by=cols).reset_index(drop=True)
    df2_sorted = df2_norm.sort_values(by=cols).reset_index(drop=True)

    # 5. Comparación con tolerancia decimal (atol=0.01 maneja los floats/183.6 vs 183.60)
    try:
        pd.testing.assert_frame_equal(
            df1_sorted,
            df2_sorted,
            check_names=False,
            check_dtype=False,
            check_exact=False,
            atol=0.01,
        )
        logger.debug("Los dataframes son equivalentes")
        return True
    except AssertionError as e:
        logger.debug(f"Se encontro la siguiente diferencia entre los dataframes:\n {e}")
        return False