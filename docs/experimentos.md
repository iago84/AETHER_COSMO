# Experimentos Propuestos (Sistema y AI)

## Comparativa de fuentes
- Objetivo: Evaluar propagación y energía para `gaussian_pulse`, `periodic`, `stochastic`, `top_hat`, `lorentzian`.
- Diseño: Misma malla y parámetros (nx, ny, dt, steps), varia `source_kind` y parámetros clave (sigma/radius/gamma).
- Métricas: energía final/temporal, espectro radial, autocorrelación 2D.
- Resultado esperado: perfiles espectrales característicos por fuente; correlaciones más amplias para top-hat/lorentziana.

## Estudio de condiciones de contorno
- Objetivo: Medir efectos de reflection/absorción en `periodic`, `fixed`, `absorbing`.
- Diseño: Fuente pulsada centrada; comparar energía en bordes y espectro.
- Métricas: energía vs tiempo, energía en anillos periféricos, espectro.

## Barrido de parámetros (diff, dt, lam, noise)
- Objetivo: Analizar estabilidad y suavizado.
- Diseño: grid de {diff, dt, lam, noise}; guardar series con stride fijo.
- Métricas: energía media, varianza, decaimiento de correlación, cambio del pico espectral.
- Resultado: mapas calor de energía/correlación vs parámetros.

## Efecto del ruido
- Objetivo: Impacto del `noise` en estructuras espaciales.
- Diseño: runs con noise ∈ {0, 0.01, 0.05, 0.1}; fuente periodic.
- Métricas: crecimiento de potencia en alta k; reducción de autocorrelación.

## Dinámica transitoria vs régimen estacionario
- Objetivo: Caracterizar convergencia temporal.
- Diseño: series largas con periodic, medir energía y espectro en ventanas.
- Métricas: tiempo hasta estacionariedad; deriva del pico espectral.

## Experimentos con AI (extensiones)
- Predicción temporal:
  - Entrenar modelos (LSTM/Temporal CNN/Transformer) sobre series NPZ para predecir frames futuros.
  - Métrica: MSE/PSNR sobre frames; fidelidad espectral.
- Inferencia de parámetros:
  - Regresor que, dado un segmento de la serie, infiere (dt, diff, lam, sigma/gamma/radius).
  - Métrica: error MAE/MAPE por parámetro, robustez a ruido.
- Detección de eventos:
  - Clasificador que detecte aparición de patrones (picos de energía, anillos en espectro).
  - Métrica: precisión/recuperación, F1, tasa de falsos positivos.

## Protocolo de ejecución
1) Crear experimento y configurar parámetros (UI o API).
2) Activar `save_series=true` con `series_stride` adecuado.
3) Ejecutar runs en cola (RQ) para barridos extensos.
4) Recopilar NPZ/JSON; exportar CSV de métricas desde la UI.
5) Analizar espectros y autocorrelaciones; si aplica, entrenar modelos AI con las series.

## Reporte de resultados
- Incluir resumen de parámetros, artefactos (PNG, CSV), y gráficos:
  - Energía vs tiempo (varias condiciones).
  - Espectro radial comparado (por fuente o parámetro).
  - Autocorrelación 2D recortada.

