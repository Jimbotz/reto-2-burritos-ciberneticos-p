// Los 3 errores más relevantes del modelo anterior que Validat3B ya corrige, en orden de importancia.
// Para agregar uno, guarda la captura de pantalla en src/assets/errores/ e impórtala aquí, por ejemplo:
//   import error1 from './assets/errores/error-1.png'
//   { titulo: 'Etiqueta de otra presentación', antes: 'Aprobada', ahora: 'Rechazada · PRODUCTO_NO_COINCIDE',
//     porque: 'La etiqueta dice 900 g y el empaque es de 1 kg.', imagen: error1 },
export type ErrorCorregido = { titulo: string; antes: string; ahora: string; porque: string; imagen?: string }

export const ERRORES: ErrorCorregido[] = []
