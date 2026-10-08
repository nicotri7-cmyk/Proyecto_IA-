/**
 * admin.js - Lógica del Panel de Administración de Base de Datos SQLite (Voice Bistro)
 * Proporciona interfaz gráfica completa para agregar productos, modificar precios,
 * controlar stock y subir o asociar imágenes.
 */

document.addEventListener('DOMContentLoaded', () => {
  // Estado local
  let productos = [];
  let categorias = [];
  let productoEnEliminacion = null;
  let vistaActual = 'table'; // Por defecto en 'table' | 'grid'
  let imagenUrlActual = '';

  // Elementos DOM
  const gridView = document.getElementById('admin-grid-view');
  const tableView = document.getElementById('admin-table-view');
  const tableTbody = document.getElementById('admin-table-tbody');
  const searchInput = document.getElementById('admin-search-input');
  const categoryFilter = document.getElementById('admin-category-filter');
  const stockFilter = document.getElementById('admin-stock-filter');
  const roleFilter = document.getElementById('admin-role-filter');
  const dietFilter = document.getElementById('admin-diet-filter');
  const btnToggleGrid = document.getElementById('btn-toggle-grid');
  const btnToggleTable = document.getElementById('btn-toggle-table');
  const btnRefreshAdmin = document.getElementById('btn-refresh-admin');
  const btnOpenCreateModal = document.getElementById('btn-open-create-modal');

  // Métricas
  const metricTotalProds = document.getElementById('metric-total-prods');
  const metricTotalStock = document.getElementById('metric-total-stock');
  const metricAgotados = document.getElementById('metric-agotados');
  const metricStockBajo = document.getElementById('metric-stock-bajo');
  const metricDesactivados = document.getElementById('metric-desactivados');
  const metricValorInv = document.getElementById('metric-valor-inv');

  // Modal Producto
  const modalProducto = document.getElementById('modal-producto');
  const modalProductoTitle = document.getElementById('modal-producto-title');
  const btnCloseProductoModal = document.getElementById('btn-close-producto-modal');
  const btnCancelModal = document.getElementById('btn-cancel-modal');
  const formProducto = document.getElementById('form-producto');
  const prodId = document.getElementById('prod-id');
  const prodNombre = document.getElementById('prod-nombre');
  const prodCategoria = document.getElementById('prod-categoria');
  const prodPrecio = document.getElementById('prod-precio');
  const prodStock = document.getElementById('prod-stock');
  const prodActivo = document.getElementById('prod-activo');
  const prodTipoPersonalizado = document.getElementById('prod-tipo-personalizado');
  const prodEsVegetariano = document.getElementById('prod-es-vegetariano');
  const prodEsVegano = document.getElementById('prod-es-vegano');
  const roleBadgePreview = document.getElementById('role-badge-preview');
  const prodImagenUrl = document.getElementById('prod-imagen-url');
  const fileInputImage = document.getElementById('file-input-image');
  const dropZone = document.getElementById('drop-zone');
  const imgPreviewBox = document.getElementById('img-preview-box');
  const imgPreviewTag = document.getElementById('img-preview-tag');
  const btnRemoveImg = document.getElementById('btn-remove-img');
  const btnSaveProduct = document.getElementById('btn-save-product');

  // Modal Eliminar
  const modalEliminar = document.getElementById('modal-eliminar');
  const deleteConfirmText = document.getElementById('delete-confirm-text');
  const btnCancelDelete = document.getElementById('btn-cancel-delete');
  const btnConfirmDelete = document.getElementById('btn-confirm-delete');

  // =========================================================
  // 1. CARGA DE DATOS Y MÉTRICAS
  // =========================================================
  async function cargarMetricas() {
    try {
      const res = await fetch('/api/admin/metricas');
      if (!res.ok) return;
      const data = await res.json();

      metricTotalProds.textContent = data.total_productos;
      metricTotalStock.textContent = `${data.total_stock} u.`;
      metricAgotados.textContent = data.productos_agotados;
      metricStockBajo.textContent = data.productos_stock_bajo;
      if (metricDesactivados) metricDesactivados.textContent = data.productos_desactivados || 0;
      metricValorInv.textContent = formatearMoneda(data.valor_inventario);

      // Actualizar opciones de categoría
      categorias = data.categorias || [];
      const valorSeleccionado = categoryFilter.value;
      categoryFilter.innerHTML = '<option value="">Todas las Categorías</option>';
      categorias.forEach((cat) => {
        const opt = document.createElement('option');
        opt.value = cat;
        opt.textContent = cat;
        if (cat === valorSeleccionado) opt.selected = true;
        categoryFilter.appendChild(opt);
      });
    } catch (e) {
      console.warn('Error al cargar métricas:', e);
    }
  }

  async function cargarCatalogo() {
    try {
      const res = await fetch('/api/productos');
      if (!res.ok) throw new Error('Error al consultar /api/productos');
      productos = await res.json();
      aplicarFiltrosYRenderizar();
      cargarMetricas();
    } catch (e) {
      console.error('Error al cargar catálogo:', e);
      gridView.innerHTML = `<div style="grid-column: 1/-1; text-align:center; padding: 3rem; color: #f87171;">
        Hubo un problema al consultar la base de datos SQLite. Por favor refresca la página.
      </div>`;
      showToast('Error al conectar con la base de datos', 'error');
    }
  }

  // =========================================================
  // 2. FILTRADO Y RENDERIZADO
  // =========================================================
  function aplicarFiltrosYRenderizar() {
    const texto = searchInput.value.toLowerCase().trim();
    const cat = categoryFilter.value;
    const stockModo = stockFilter.value;
    const rolModo = roleFilter ? roleFilter.value : 'todos';
    const dietaModo = dietFilter ? dietFilter.value : 'todos';

    const filtrados = productos.filter((p) => {
      // Filtro texto
      const coincideTexto = !texto || p.nombre.toLowerCase().includes(texto) || p.categoria.toLowerCase().includes(texto);

      // Filtro categoría
      const coincideCat = !cat || p.categoria === cat;

      // Filtro stock y estado activo
      let coincideStock = true;
      if (stockModo === 'activos') coincideStock = p.activo !== false;
      else if (stockModo === 'desactivados') coincideStock = p.activo === false;
      else if (stockModo === 'disponible') coincideStock = p.stock_disponible > 3 && p.activo !== false;
      else if (stockModo === 'bajo') coincideStock = p.stock_disponible > 0 && p.stock_disponible <= 3 && p.activo !== false;
      else if (stockModo === 'agotado') coincideStock = p.stock_disponible <= 0 && p.activo !== false;

      // Filtro rol en sandwich
      let coincideRol = true;
      const rolActual = p.tipo_personalizado || 'ninguno';
      if (rolModo !== 'todos') {
        coincideRol = rolActual === rolModo;
      }

      // Filtro preferencia dietética
      let coincideDieta = true;
      if (dietaModo === 'vegetariano') {
        coincideDieta = Boolean(p.es_vegetariano);
      } else if (dietaModo === 'vegano') {
        coincideDieta = Boolean(p.es_vegano);
      } else if (dietaModo === 'no-vegetariano') {
        coincideDieta = !p.es_vegetariano && !p.es_vegano;
      }

      return coincideTexto && coincideCat && coincideStock && coincideRol && coincideDieta;
    });

    // Sincronizar visibilidad de vistas
    if (vistaActual === 'table') {
      gridView.style.display = 'none';
      tableView.style.display = 'block';
      btnToggleTable.classList.add('active');
      btnToggleGrid.classList.remove('active');
    } else {
      gridView.style.display = 'grid';
      tableView.style.display = 'none';
      btnToggleGrid.classList.add('active');
      btnToggleTable.classList.remove('active');
    }

    renderizarGrid(filtrados);
    renderizarTable(filtrados);
  }

  function renderizarGrid(lista) {
    if (lista.length === 0) {
      gridView.innerHTML = `
        <div style="grid-column: 1/-1; text-align: center; padding: 4rem 1rem; color: var(--text-muted);">
          <div style="font-size: 2.5rem; margin-bottom: 0.5rem;">🔍</div>
          <p style="font-size: 1.05rem; font-weight: 600;">No se encontraron productos con los filtros seleccionados.</p>
          <small>Prueba buscando otro término o restablece los filtros.</small>
        </div>
      `;
      return;
    }

    gridView.innerHTML = '';
    lista.forEach((prod) => {
      const isInactive = prod.activo === false;
      const isOut = prod.stock_disponible <= 0;
      const isLow = !isOut && prod.stock_disponible <= 3;

      const card = document.createElement('div');
      card.className = `admin-prod-card ${isInactive ? 'card-inactive' : (isOut ? 'out-of-stock' : (isLow ? 'low-stock' : ''))}`;

      const imgHtml = prod.imagen_url
        ? `<img src="${escapeHtml(prod.imagen_url)}" alt="${escapeHtml(prod.nombre)}" loading="lazy" onerror="this.parentElement.innerHTML='<div class=\\'admin-img-fallback\\'>🍽️</div>'" />`
        : `<div class="admin-img-fallback">🍽️</div>`;

      const overlayHtml = isInactive ? '<span class="admin-status-overlay">DESACTIVADO</span>' : '';

      const rol = prod.tipo_personalizado || 'ninguno';
      let roleBadgeHtml = '';
      if (rol === 'base') {
        roleBadgeHtml = '<span class="admin-role-badge badge-role-base" style="position:absolute;bottom:0.6rem;left:0.6rem;">🥖 Base (Pan)</span>';
      } else if (rol === 'ingrediente') {
        roleBadgeHtml = '<span class="admin-role-badge badge-role-ingrediente" style="position:absolute;bottom:0.6rem;left:0.6rem;">🥑 Ingrediente</span>';
      }

      let dietBadgesHtml = '';
      if (prod.es_vegano) {
        dietBadgesHtml += '<span class="admin-diet-badge badge-diet-vegano" title="Apto Vegano">🌿 Vegano</span>';
      }
      if (prod.es_vegetariano && !prod.es_vegano) {
        dietBadgesHtml += '<span class="admin-diet-badge badge-diet-vegetariano" title="Apto Vegetariano">🌱 Vegetariano</span>';
      }

      card.innerHTML = `
        <div class="admin-card-img-box">
          ${imgHtml}
          ${overlayHtml}
          ${roleBadgeHtml}
          <span class="admin-cat-tag">${escapeHtml(prod.categoria)}</span>
          <span class="admin-id-tag">#${prod.id}</span>
        </div>

        <div class="admin-card-content">
          <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:0.5rem;margin-bottom:0.4rem;">
            <h3 class="admin-prod-name" style="margin-bottom:0;">${escapeHtml(prod.nombre)}</h3>
            <div style="display:flex;gap:0.25rem;flex-wrap:wrap;flex-shrink:0;">${dietBadgesHtml}</div>
          </div>

          <div class="admin-quick-controls">
            <div class="quick-field">
              <span class="quick-label">Precio</span>
              <div class="quick-price-box">
                <span>${formatearMoneda(prod.precio)}</span>
              </div>
            </div>

            <div class="quick-field">
              <span class="quick-label">Stock Actual</span>
              <div class="quick-stock-stepper">
                <button type="button" class="btn-step btn-stock-dec" data-id="${prod.id}" title="Restar 1 unidad">-</button>
                <input type="number" class="stock-input-mini" data-id="${prod.id}" value="${prod.stock_disponible}" min="0" />
                <button type="button" class="btn-step btn-stock-inc" data-id="${prod.id}" title="Sumar 1 unidad">+</button>
              </div>
            </div>
          </div>

          <div class="admin-card-actions">
            <button type="button" class="btn-admin-action ${isInactive ? 'btn-status-activate' : 'btn-status-deactivate'} btn-grid-toggle" data-id="${prod.id}" title="${isInactive ? 'Activar en la carta' : 'Desactivar de la carta'}">
              <span>${isInactive ? '✅' : '🚫'}</span>
              <span>${isInactive ? 'Activar' : 'Desactivar'}</span>
            </button>
            <button type="button" class="btn-admin-action btn-edit-prod" data-id="${prod.id}">
              <span>✏️</span>
              <span>Editar</span>
            </button>
            <button type="button" class="btn-admin-action btn-delete btn-delete-prod" data-id="${prod.id}" data-name="${escapeHtml(prod.nombre)}">
              <span>🗑️</span>
              <span>Eliminar</span>
            </button>
          </div>
        </div>
      `;

      // Eventos de stepper de stock
      const btnDec = card.querySelector('.btn-stock-dec');
      const btnInc = card.querySelector('.btn-stock-inc');
      const stockInput = card.querySelector('.stock-input-mini');
      const btnToggle = card.querySelector('.btn-grid-toggle');
      const btnEdit = card.querySelector('.btn-edit-prod');
      const btnDel = card.querySelector('.btn-delete-prod');

      btnDec.addEventListener('click', () => ajustarStockRapido(prod.id, prod.stock_disponible - 1));
      btnInc.addEventListener('click', () => ajustarStockRapido(prod.id, prod.stock_disponible + 1));
      stockInput.addEventListener('change', (e) => {
        const val = parseInt(e.target.value, 10);
        if (!isNaN(val)) ajustarStockRapido(prod.id, val);
      });

      if (btnToggle) btnToggle.addEventListener('click', () => toggleEstadoProducto(prod.id));
      btnEdit.addEventListener('click', () => abrirModalEditar(prod));
      btnDel.addEventListener('click', () => abrirModalEliminar(prod));

      gridView.appendChild(card);
    });
  }

  function renderizarTable(lista) {
    if (lista.length === 0) {
      tableTbody.innerHTML = `
        <tr>
          <td colspan="8" style="text-align: center; padding: 2.5rem; color: var(--text-muted);">
            No hay productos que coincidan con la búsqueda.
          </td>
        </tr>
      `;
      return;
    }

    tableTbody.innerHTML = '';
    lista.forEach((prod) => {
      const isInactive = prod.activo === false;
      const isOut = prod.stock_disponible <= 0;
      const isLow = !isOut && prod.stock_disponible <= 3;

      const tr = document.createElement('tr');
      if (isInactive) tr.className = 'row-inactive';

      const imgHtml = prod.imagen_url
        ? `<img class="table-thumb" src="${escapeHtml(prod.imagen_url)}" alt="${escapeHtml(prod.nombre)}" loading="lazy" onerror="this.src='data:image/svg+xml;utf8,<svg xmlns=\\'http://www.w3.org/2000/svg\\' width=\\'40\\' height=\\'40\\'><rect fill=\\'%23333\\' width=\\'40\\' height=\\'40\\'/><text fill=\\'%23888\\' x=\\'50%\\' y=\\'55%\\' text-anchor=\\'middle\\' font-size=\\'18\\'>🍽️</text></svg>'" />`
        : `<div class="table-thumb" style="display:flex;align-items:center;justify-content:center;font-size:1.3rem;">🍽️</div>`;

      let badgeEstado = '<span class="status-badge badge-active">🟢 Activo</span>';
      if (isInactive) badgeEstado = '<span class="status-badge badge-inactive">⚪ Desactivado</span>';
      else if (isOut) badgeEstado = '<span class="status-badge badge-out">🔴 Agotado</span>';
      else if (isLow) badgeEstado = '<span class="status-badge badge-low">🟡 Crítico</span>';

      const btnToggleHtml = isInactive
        ? `<button type="button" class="btn-admin-action btn-status-activate btn-table-toggle" style="display:inline-flex;margin-right:0.35rem;" data-id="${prod.id}" title="Activar producto en la carta">✅ Activar</button>`
        : `<button type="button" class="btn-admin-action btn-status-deactivate btn-table-toggle" style="display:inline-flex;margin-right:0.35rem;" data-id="${prod.id}" title="Desactivar producto de la carta">🚫 Desactivar</button>`;

      const rol = prod.tipo_personalizado || 'ninguno';
      let roleBadgeTable = '';
      if (rol === 'base') {
        roleBadgeTable = '<span class="admin-role-badge badge-role-base" style="margin-left:0.4rem;font-size:0.72rem;">🥖 Base</span>';
      } else if (rol === 'ingrediente') {
        roleBadgeTable = '<span class="admin-role-badge badge-role-ingrediente" style="margin-left:0.4rem;font-size:0.72rem;">🥑 Ingrediente</span>';
      }

      let dietBadgesTable = '';
      if (prod.es_vegano) {
        dietBadgesTable += '<span class="admin-diet-badge badge-diet-vegano" style="margin-left:0.35rem;font-size:0.72rem;">🌿 Vegano</span>';
      }
      if (prod.es_vegetariano && !prod.es_vegano) {
        dietBadgesTable += '<span class="admin-diet-badge badge-diet-vegetariano" style="margin-left:0.35rem;font-size:0.72rem;">🌱 Veg</span>';
      }

      tr.innerHTML = `
        <td style="width: 60px;">${imgHtml}</td>
        <td style="font-family: var(--font-mono); color: var(--text-muted);">#${prod.id}</td>
        <td><strong>${escapeHtml(prod.nombre)}</strong> ${roleBadgeTable} ${dietBadgesTable}</td>
        <td><span class="admin-cat-tag" style="position:static;display:inline-block;">${escapeHtml(prod.categoria)}</span></td>
        <td style="font-family: var(--font-mono); font-weight:700; color:#34d399;">${formatearMoneda(prod.precio)}</td>
        <td>
          <div class="quick-stock-stepper" style="display:inline-flex;">
            <button type="button" class="btn-step btn-table-dec" data-id="${prod.id}">-</button>
            <span style="min-width: 32px; text-align: center; font-family: var(--font-mono); font-weight: 700;">${prod.stock_disponible}</span>
            <button type="button" class="btn-step btn-table-inc" data-id="${prod.id}">+</button>
          </div>
        </td>
        <td>${badgeEstado}</td>
        <td style="text-align: right; white-space: nowrap;">
          ${btnToggleHtml}
          <button type="button" class="btn-admin-action btn-table-edit" style="display:inline-flex;margin-right:0.35rem;" data-id="${prod.id}" title="Editar">
            ✏️
          </button>
          <button type="button" class="btn-admin-action btn-delete btn-table-del" style="display:inline-flex;" data-id="${prod.id}" title="Eliminar">
            🗑️
          </button>
        </td>
      `;

      tr.querySelector('.btn-table-toggle').addEventListener('click', () => toggleEstadoProducto(prod.id));
      tr.querySelector('.btn-table-dec').addEventListener('click', () => ajustarStockRapido(prod.id, prod.stock_disponible - 1));
      tr.querySelector('.btn-table-inc').addEventListener('click', () => ajustarStockRapido(prod.id, prod.stock_disponible + 1));
      tr.querySelector('.btn-table-edit').addEventListener('click', () => abrirModalEditar(prod));
      tr.querySelector('.btn-table-del').addEventListener('click', () => abrirModalEliminar(prod));

      tableTbody.appendChild(tr);
    });
  }

  // =========================================================
  // 3. ACTIVAR / DESACTIVAR PRODUCTOS EN SQLite
  // =========================================================
  async function toggleEstadoProducto(id) {
    try {
      const res = await fetch(`/api/admin/productos/${id}/estado`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
      });
      if (!res.ok) throw new Error('Error al modificar estado del producto');
      const data = await res.json();

      const p = productos.find((item) => item.id === id);
      if (p) {
        p.activo = data.activo;
      }

      aplicarFiltrosYRenderizar();
      cargarMetricas();
      if (data.activo) {
        showToast(`Producto '${data.nombre}' activado en la carta`);
      } else {
        showToast(`Producto '${data.nombre}' desactivado de la carta`);
      }
    } catch (e) {
      console.error(e);
      showToast('No se pudo actualizar el estado en SQLite', 'error');
    }
  }

  // =========================================================
  // 4. AJUSTE RÁPIDO DE STOCK EN SQLite
  // =========================================================
  async function ajustarStockRapido(id, nuevoStock) {
    nuevoStock = Math.max(0, parseInt(nuevoStock, 10) || 0);
    try {
      const res = await fetch(`/api/admin/productos/${id}/stock`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ stock_disponible: nuevoStock }),
      });

      if (!res.ok) throw new Error('Error al actualizar stock');
      const data = await res.json();

      // Actualizar estado local
      const p = productos.find((item) => item.id === id);
      if (p) {
        p.stock_disponible = data.stock_disponible;
      }

      aplicarFiltrosYRenderizar();
      cargarMetricas();
      showToast(`Stock actualizado: ${p ? p.nombre : 'Producto'} → ${nuevoStock} u.`);
    } catch (e) {
      console.error(e);
      showToast('No se pudo actualizar el stock en SQLite', 'error');
    }
  }

  // =========================================================
  // 4. SUBIDA Y GESTIÓN DE IMÁGENES
  // =========================================================
  function mostrarPrevisualizacionImagen(url) {
    if (!url) {
      imgPreviewBox.style.display = 'none';
      imgPreviewTag.src = '';
      imagenUrlActual = '';
      return;
    }
    imagenUrlActual = url;
    imgPreviewTag.src = url;
    imgPreviewBox.style.display = 'block';
  }

  btnRemoveImg.addEventListener('click', () => {
    mostrarPrevisualizacionImagen('');
    prodImagenUrl.value = '';
    fileInputImage.value = '';
  });

  // URL externa escrita
  prodImagenUrl.addEventListener('input', (e) => {
    const val = e.target.value.trim();
    if (val) {
      mostrarPrevisualizacionImagen(val);
    }
  });

  // Selector de archivo local
  dropZone.addEventListener('click', () => fileInputImage.click());

  fileInputImage.addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (file) await subirArchivoImagen(file);
  });

  // Drag & Drop
  dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('dragover');
  });

  dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));

  dropZone.addEventListener('drop', async (e) => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      await subirArchivoImagen(e.dataTransfer.files[0]);
    }
  });

  async function subirArchivoImagen(file) {
    const formData = new FormData();
    formData.append('file', file);

    showToast('Subiendo imagen al servidor...', 'info');

    try {
      const res = await fetch('/api/admin/upload-imagen', {
        method: 'POST',
        body: formData,
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Error al subir imagen');
      }

      const data = await res.json();
      prodImagenUrl.value = data.url;
      mostrarPrevisualizacionImagen(data.url);
      showToast('¡Imagen subida exitosamente!');
    } catch (err) {
      console.error(err);
      showToast(err.message || 'Error al subir la imagen', 'error');
    }
  }

  // =========================================================
  // 5. MODAL DE CREACIÓN / EDICIÓN
  // =========================================================
  function abrirModalCrear() {
    modalProductoTitle.textContent = 'Agregar Nuevo Producto';
    prodId.value = '';
    prodNombre.value = '';
    prodCategoria.value = '';
    prodPrecio.value = '';
    prodStock.value = '15';
    if (prodActivo) prodActivo.checked = true;
    if (prodTipoPersonalizado) prodTipoPersonalizado.value = 'ninguno';
    if (prodEsVegetariano) prodEsVegetariano.checked = false;
    if (prodEsVegano) prodEsVegano.checked = false;
    actualizarPreviewRol('ninguno');
    prodImagenUrl.value = '';
    fileInputImage.value = '';
    mostrarPrevisualizacionImagen('');
    btnSaveProduct.innerHTML = '<span>💾</span><span>Guardar Producto</span>';

    modalProducto.style.display = 'flex';
    prodNombre.focus();
  }

  function abrirModalEditar(prod) {
    modalProductoTitle.textContent = `Editar Producto #${prod.id}`;
    prodId.value = prod.id;
    prodNombre.value = prod.nombre;
    prodCategoria.value = prod.categoria;
    prodPrecio.value = prod.precio;
    prodStock.value = prod.stock_disponible;
    if (prodActivo) prodActivo.checked = prod.activo !== false;
    const rolActual = prod.tipo_personalizado || 'ninguno';
    if (prodTipoPersonalizado) prodTipoPersonalizado.value = rolActual;
    if (prodEsVegetariano) prodEsVegetariano.checked = Boolean(prod.es_vegetariano);
    if (prodEsVegano) prodEsVegano.checked = Boolean(prod.es_vegano);
    actualizarPreviewRol(rolActual);
    prodImagenUrl.value = prod.imagen_url || '';
    fileInputImage.value = '';
    mostrarPrevisualizacionImagen(prod.imagen_url || '');
    btnSaveProduct.innerHTML = '<span>💾</span><span>Guardar Cambios</span>';

    modalProducto.style.display = 'flex';
    prodNombre.focus();
  }

  function cerrarModalProducto() {
    modalProducto.style.display = 'none';
  }

  btnOpenCreateModal.addEventListener('click', abrirModalCrear);
  btnCloseProductoModal.addEventListener('click', cerrarModalProducto);
  btnCancelModal.addEventListener('click', cerrarModalProducto);

  // Guardar formulario (Crear o Actualizar)
  formProducto.addEventListener('submit', async (e) => {
    e.preventDefault();

    const id = prodId.value;
    const esEdicion = Boolean(id);

    const payload = {
      nombre: prodNombre.value.trim(),
      categoria: prodCategoria.value.trim(),
      precio: parseInt(prodPrecio.value, 10),
      stock_disponible: parseInt(prodStock.value, 10),
      activo: prodActivo ? prodActivo.checked : true,
      tipo_personalizado: prodTipoPersonalizado ? prodTipoPersonalizado.value : 'ninguno',
      es_vegetariano: prodEsVegetariano ? prodEsVegetariano.checked : false,
      es_vegano: prodEsVegano ? prodEsVegano.checked : false,
      imagen_url: prodImagenUrl.value.trim() || imagenUrlActual || '',
    };

    if (!payload.nombre || !payload.categoria || isNaN(payload.precio) || isNaN(payload.stock_disponible)) {
      showToast('Por favor completa todos los campos requeridos correctamente.', 'error');
      return;
    }

    try {
      const url = esEdicion ? `/api/admin/productos/${id}` : '/api/admin/productos';
      const metodo = esEdicion ? 'PUT' : 'POST';

      btnSaveProduct.disabled = true;
      btnSaveProduct.innerHTML = '<span>⏳</span><span>Guardando...</span>';

      const res = await fetch(url, {
        method: metodo,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || 'Error al guardar producto');
      }

      const guardado = await res.json();
      cerrarModalProducto();
      showToast(esEdicion ? `¡Producto '${guardado.nombre}' actualizado!` : `¡Producto '${guardado.nombre}' creado con éxito!`);
      cargarCatalogo();
    } catch (err) {
      console.error(err);
      showToast(err.message || 'Error al guardar en SQLite', 'error');
    } finally {
      btnSaveProduct.disabled = false;
      btnSaveProduct.innerHTML = '<span>💾</span><span>Guardar Producto</span>';
    }
  });

  // =========================================================
  // 6. MODAL DE ELIMINACIÓN
  // =========================================================
  function abrirModalEliminar(prod) {
    productoEnEliminacion = prod;
    deleteConfirmText.textContent = `¿Estás seguro de que deseas eliminar permanentemente '${prod.nombre}' (ID #${prod.id}) de la base de datos SQLite?`;
    modalEliminar.style.display = 'flex';
  }

  function cerrarModalEliminar() {
    modalEliminar.style.display = 'none';
    productoEnEliminacion = null;
  }

  btnCancelDelete.addEventListener('click', cerrarModalEliminar);

  btnConfirmDelete.addEventListener('click', async () => {
    if (!productoEnEliminacion) return;

    const id = productoEnEliminacion.id;
    const nombre = productoEnEliminacion.nombre;

    try {
      btnConfirmDelete.disabled = true;
      btnConfirmDelete.textContent = 'Eliminando...';

      const res = await fetch(`/api/admin/productos/${id}`, {
        method: 'DELETE',
      });

      if (!res.ok) throw new Error('Error al eliminar producto');

      cerrarModalEliminar();
      showToast(`Producto '${nombre}' eliminado del inventario.`);
      cargarCatalogo();
    } catch (err) {
      console.error(err);
      showToast('No se pudo eliminar el producto de SQLite.', 'error');
    } finally {
      btnConfirmDelete.disabled = false;
      btnConfirmDelete.innerHTML = '<span>🗑️</span><span>Sí, Eliminar</span>';
    }
  });

  function actualizarPreviewRol(rol) {
    if (!roleBadgePreview) return;
    if (rol === 'base') {
      roleBadgePreview.className = 'admin-role-badge badge-role-base';
      roleBadgePreview.textContent = '🥖 Base (Pan)';
    } else if (rol === 'ingrediente') {
      roleBadgePreview.className = 'admin-role-badge badge-role-ingrediente';
      roleBadgePreview.textContent = '🥑 Ingrediente';
    } else {
      roleBadgePreview.className = 'admin-role-badge badge-role-none';
      roleBadgePreview.textContent = '📦 Regular';
    }
  }

  if (prodTipoPersonalizado) {
    prodTipoPersonalizado.addEventListener('change', (e) => {
      actualizarPreviewRol(e.target.value);
    });
  }

  // Sincronización amigable de checkboxes: todo lo vegano es vegetariano
  if (prodEsVegano && prodEsVegetariano) {
    prodEsVegano.addEventListener('change', () => {
      if (prodEsVegano.checked) {
        prodEsVegetariano.checked = true;
      }
    });
    prodEsVegetariano.addEventListener('change', () => {
      if (!prodEsVegetariano.checked) {
        prodEsVegano.checked = false;
      }
    });
  }

  // =========================================================
  // 7. VISTAS Y FILTROS EN TIEMPO REAL
  // =========================================================
  searchInput.addEventListener('input', aplicarFiltrosYRenderizar);
  categoryFilter.addEventListener('change', aplicarFiltrosYRenderizar);
  stockFilter.addEventListener('change', aplicarFiltrosYRenderizar);
  if (roleFilter) roleFilter.addEventListener('change', aplicarFiltrosYRenderizar);
  if (dietFilter) dietFilter.addEventListener('change', aplicarFiltrosYRenderizar);
  btnRefreshAdmin.addEventListener('click', () => {
    cargarCatalogo();
    showToast('Catálogo sincronizado.');
  });

  btnToggleGrid.addEventListener('click', () => {
    vistaActual = 'grid';
    btnToggleGrid.classList.add('active');
    btnToggleTable.classList.remove('active');
    gridView.style.display = 'grid';
    tableView.style.display = 'none';
  });

  btnToggleTable.addEventListener('click', () => {
    vistaActual = 'table';
    btnToggleTable.classList.add('active');
    btnToggleGrid.classList.remove('active');
    gridView.style.display = 'none';
    tableView.style.display = 'block';
  });

  // =========================================================
  // 8. UTILIDADES
  // =========================================================
  function formatearMoneda(monto) {
    return new Intl.NumberFormat('es-CL', {
      style: 'currency',
      currency: 'CLP',
      maximumFractionDigits: 0,
    }).format(monto || 0);
  }

  function escapeHtml(text) {
    if (!text) return '';
    return String(text)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function showToast(mensaje, tipo = 'success') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast ${tipo}`;
    const icon = tipo === 'success' ? '✅' : (tipo === 'error' ? '❌' : 'ℹ️');
    toast.innerHTML = `<span>${icon}</span><span>${escapeHtml(mensaje)}</span>`;

    container.appendChild(toast);

    setTimeout(() => {
      toast.style.transition = 'all 0.3s ease';
      toast.style.opacity = '0';
      toast.style.transform = 'translateX(50px)';
      setTimeout(() => toast.remove(), 300);
    }, 3200);
  }

  // Carga inicial
  cargarCatalogo();
});
