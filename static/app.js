/**
 * app.js - Lógica del Frontend del Kiosco de Pedidos Voice Bistro
 * Maneja el router multi-vista (Bienvenida, Autoservicio IA, Menú Tradicional),
 * interacción por voz con Web Speech API, adición directa al carrito y sincronización de SQLite.
 */

document.addEventListener('DOMContentLoaded', () => {
  // Estado global de la aplicación
  let sessionId = getOrCreateSessionId();
  let isRecording = false;
  let voiceMuted = false;
  let recognition = null;
  let spanishVoice = null;
  let catalogoProductos = [];
  let categoriaSeleccionada = 'Sandwiches';
  let totalMensajes = 0;
  let productosOfrecidosActuales = [];

  // =========================================================
  // ELEMENTOS DEL DOM
  // =========================================================
  // Vistas principales
  const viewWelcome = document.getElementById('view-welcome');
  const viewAiKiosk = document.getElementById('view-ai-kiosk');
  const viewTraditionalMenu = document.getElementById('view-traditional-menu');

  // Botones de navegación entre vistas
  const btnGotoAi = document.getElementById('btn-goto-ai');
  const btnGotoMenu = document.getElementById('btn-goto-menu');
  const btnAiBackWelcome = document.getElementById('btn-ai-back-welcome');
  const btnMenuBackWelcome = document.getElementById('btn-menu-back-welcome');

  // Autoservicio IA (Boceto Imagen 2)
  const btnMic = document.getElementById('btn-mic');
  const soundWave = document.getElementById('sound-wave');
  const statusTag = document.getElementById('status-tag');
  const statusDesc = document.getElementById('status-desc');
  const micCaptionText = document.getElementById('mic-caption-text');
  const aiResponseText = document.getElementById('ai-response-text');
  const aiEmptyPrompt = document.getElementById('ai-empty-prompt');
  const chatForm = document.getElementById('chat-form');
  const userTextInput = document.getElementById('user-text-input');
  const aiOfferedSection = document.getElementById('ai-offered-section');
  const aiCardsGrid = document.getElementById('ai-cards-grid');
  const btnCleanOffered = document.getElementById('btn-clean-offered');
  const ticketSessionId = document.getElementById('ticket-session-id');
  const btnToggleVoice = document.getElementById('btn-toggle-voice');
  const voiceIcon = document.getElementById('voice-icon');
  const voiceLabel = document.getElementById('voice-label');
  const btnNuevoPedido = document.getElementById('btn-nuevo-pedido');

  // Botón Carrito Gigante (Imagen 2) y Subnav Carrito
  const btnAiOpenCart = document.getElementById('btn-ai-open-cart');
  const aiCartCountBadge = document.getElementById('ai-cart-count-badge');
  const aiCartTotalBadge = document.getElementById('ai-cart-total-badge');
  const btnMenuOpenCart = document.getElementById('btn-menu-open-cart');
  const menuCartCountBadge = document.getElementById('menu-cart-count-badge');
  const menuCartTotalBadge = document.getElementById('menu-cart-total-badge');

  // Cajón Lateral del Carrito (Slide-over Drawer)
  const cartDrawer = document.getElementById('cart-drawer');
  const btnCloseCart = document.getElementById('btn-close-cart');
  const btnKeepOrdering = document.getElementById('btn-keep-ordering');
  const orderTbody = document.getElementById('order-items-tbody');
  const summaryTotalItems = document.getElementById('summary-total-items');
  const summaryTotalAmount = document.getElementById('summary-total-amount');
  const btnConfirmarPedido = document.getElementById('btn-confirmar-pedido');
  const drawerSessionTag = document.getElementById('drawer-session-tag');

  // Modal de Confirmación
  const modalConfirmacion = document.getElementById('modal-confirmacion');
  const btnCerrarModal = document.getElementById('btn-cerrar-modal');
  const modalTotalBox = document.getElementById('modal-total-box');

  // Menú Tradicional estilo Totem
  const totemProductsGrid = document.getElementById('totem-products-grid');
  const categoryTabs = document.querySelectorAll('.cat-tab-btn');

  // Modal de Armado de Sandwich Personalizado (Paso a Paso)
  const modalCustomSandwich = document.getElementById('modal-custom-sandwich');
  const btnCloseCustomBuilder = document.getElementById('btn-close-custom-builder');
  const stepInd1 = document.getElementById('step-ind-1');
  const stepInd2 = document.getElementById('step-ind-2');
  const step2Subtitle = document.getElementById('step-2-subtitle');
  const sectionStepBase = document.getElementById('section-step-base');
  const baseStatusBadge = document.getElementById('base-status-badge');
  const builderBasesGrid = document.getElementById('builder-bases-grid');
  const sectionStepIngredients = document.getElementById('section-step-ingredients');
  const ingredientsCountBadge = document.getElementById('ingredients-count-badge');
  const builderLockedOverlay = document.getElementById('builder-locked-overlay');
  const builderIngredientsGrid = document.getElementById('builder-ingredients-grid');
  const builderSelectedBaseName = document.getElementById('builder-selected-base-name');
  const builderSelectedIngredientsSummary = document.getElementById('builder-selected-ingredients-summary');
  const builderTotalPrice = document.getElementById('builder-total-price');
  const btnBuilderConfirm = document.getElementById('btn-builder-confirm');

  // Pantalla de Pago CLIFF
  const modalPago = document.getElementById('modal-pago');
  const btnCerrarPago = document.getElementById('btn-cerrar-pago');
  const btnCancelarPago = document.getElementById('btn-cancelar-pago');
  const btnFinalizarPagoAhora = document.getElementById('btn-finalizar-pago-ahora');
  const pagoItemsList = document.getElementById('pago-items-list');
  const pagoItemsCount = document.getElementById('pago-items-count');
  const pagoTotalAmount = document.getElementById('pago-total-amount');

  // Elementos UI CLIFF
  const cliffFloatingSearchBtn = document.getElementById('cliff-floating-search-btn');
  const cliffCategoryHeading = document.getElementById('cliff-current-category-heading');
  const btnShareWelcome = document.getElementById('btn-share-welcome');
  const btnShareAi = document.getElementById('btn-share-ai');
  const btnShareMenu = document.getElementById('btn-share-menu');

  // Último pedido en memoria
  let ultimoPedidoEnMemoria = { items: [], total: 0 };

  // Descripciones detalladas de sandwiches y productos CLIFF (idénticas a la referencia)
  const DESCRIPCIONES_CLIFF = {
    'Chacarero Mortal': '120g de Carne, 80g de Tomate, 40g de P. Verdes, 15g Ají Verde, 20g Mayonesa.',
    'Diputado Vulcano': '160g de Carne, 1 Huevo, 30g de queso fundido.',
    'Barros Luco': '100g de Carne, 30g de queso Fundido, 80g Mayonesa Lactonesa.',
    'Asiento Italiano': '100g de Carne de Asiento Nacional, 40g de palta, 40g de tomate.',
    'Carne Magra': '140g de carne de asiento nacional, 80g de mayo casera.',
    'Hamburguesa Clásica': 'Carne seleccionada, lechuga fresca, tomate y aderezo especial CLIFF.',
    'Hamburguesa Doble Queso': 'Doble porción de carne con doble queso fundido artesanal.',
    'Sandwich Mechada Palta': 'Carne mechada de cocción lenta y abundante palta hass fresca.',
    'Empanada de Pino Horno': 'Clásica empanada chilena al horno rellena con pino tradicional y aceituna.',
    'Papas Fritas Medianas': 'Papas rústicas doradas y crujientes con sal de mar.',
    'Papas Rústicas Cheddar': 'Papas rústicas bañadas en salsa cheddar caliente artesanal.',
    'Aros de Cebolla Crujientes': 'Aros de cebolla rebozados y dorados al punto perfecto.',
  };

  // Estado local del Armador de Sandwich Personalizado
  let builderBases = [];
  let builderIngredients = [];
  let builderSelectedBase = null;
  let builderSelectedIngredients = new Map();


  // =========================================================
  // 1. GESTIÓN DE SESIÓN
  // =========================================================
  function getOrCreateSessionId() {
    let sid = sessionStorage.getItem('kiosk_session_id');
    if (!sid) {
      sid = (typeof crypto !== 'undefined' && crypto.randomUUID) 
        ? crypto.randomUUID() 
        : 'sesion-' + Math.random().toString(36).substring(2, 10);
      sessionStorage.setItem('kiosk_session_id', sid);
    }
    return sid;
  }

  function actualizarEtiquetasSesion() {
    const sesionCorta = `Sesión #${sessionId.slice(0, 8)}`;
    if (ticketSessionId) ticketSessionId.textContent = sesionCorta;
    if (drawerSessionTag) drawerSessionTag.textContent = sesionCorta;
  }
  actualizarEtiquetasSesion();

  // =========================================================
  // 2. ROUTER DE VISTAS (SPA)
  // =========================================================
  function mostrarVista(vista) {
    if (viewWelcome) viewWelcome.classList.remove('active');
    if (viewAiKiosk) viewAiKiosk.classList.remove('active');
    if (viewTraditionalMenu) viewTraditionalMenu.classList.remove('active');

    if (viewWelcome) viewWelcome.style.display = 'none';
    if (viewAiKiosk) viewAiKiosk.style.display = 'none';
    if (viewTraditionalMenu) viewTraditionalMenu.style.display = 'none';

    if (vista === 'welcome') {
      if (viewWelcome) {
        viewWelcome.classList.add('active');
        viewWelcome.style.display = 'flex';
      }
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } else if (vista === 'ai-kiosk' || vista === 'ai') {
      if (viewAiKiosk) {
        viewAiKiosk.classList.add('active');
        viewAiKiosk.style.display = 'flex';
      }
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } else if (vista === 'traditional-menu' || vista === 'menu') {
      if (viewTraditionalMenu) {
        viewTraditionalMenu.classList.add('active');
        viewTraditionalMenu.style.display = 'flex';
      }
      cargarCatalogoTotem();
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }
  }

  // Eventos de navegación entre pantallas
  if (btnGotoAi) btnGotoAi.addEventListener('click', () => mostrarVista('ai-kiosk'));
  if (btnGotoMenu) btnGotoMenu.addEventListener('click', () => mostrarVista('traditional-menu'));
  if (btnAiBackWelcome) btnAiBackWelcome.addEventListener('click', () => mostrarVista('welcome'));
  if (btnMenuBackWelcome) btnMenuBackWelcome.addEventListener('click', () => mostrarVista('welcome'));

  // =========================================================
  // 3. CAJÓN LATERAL DEL CARRITO (SLIDE-OVER DRAWER)
  // =========================================================
  function abrirCarrito() {
    if (cartDrawer) {
      cartDrawer.style.display = 'flex';
    }
  }

  function cerrarCarrito() {
    if (cartDrawer) {
      cartDrawer.style.display = 'none';
    }
  }

  if (btnAiOpenCart) btnAiOpenCart.addEventListener('click', abrirCarrito);
  if (btnMenuOpenCart) btnMenuOpenCart.addEventListener('click', abrirCarrito);
  if (btnCloseCart) btnCloseCart.addEventListener('click', cerrarCarrito);
  if (btnKeepOrdering) btnKeepOrdering.addEventListener('click', cerrarCarrito);

  if (cartDrawer) {
    cartDrawer.addEventListener('click', (e) => {
      if (e.target === cartDrawer) {
        cerrarCarrito();
      }
    });
  }

  // =========================================================
  // 4. CONFIGURACIÓN DE VOZ (SPEECH RECOGNITION & SYNTHESIS)
  // =========================================================
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

  if (SpeechRecognition) {
    recognition = new SpeechRecognition();
    recognition.lang = 'es-CL';
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;

    recognition.onstart = () => {
      isRecording = true;
      if (btnMic) btnMic.classList.add('recording');
      if (soundWave) soundWave.classList.add('active');
      if (statusTag) {
        statusTag.className = 'status-indicator-tag recording';
        statusTag.textContent = 'Escuchando...';
      }
      if (statusDesc) statusDesc.textContent = 'Habla ahora con naturalidad...';
      if (micCaptionText) micCaptionText.textContent = '🔴 Escuchando...';
    };

    recognition.onresult = (event) => {
      const speechResult = event.results[0][0].transcript;
      console.log('[SPEECH IN] Reconocido:', speechResult);
      if (speechResult && speechResult.trim()) {
        procesarMensajeUsuario(speechResult);
      }
    };

    recognition.onerror = (event) => {
      console.warn('[SPEECH ERROR]', event.error);
      resetearEstadoMicrofono();
      if (event.error === 'not-allowed') {
        alert('Permiso de micrófono bloqueado. Habilítalo en el navegador o usa el teclado.');
      } else if (event.error === 'no-speech') {
        if (statusDesc) statusDesc.textContent = 'No detecté voz. Presiona el micrófono para intentar de nuevo.';
      }
    };

    recognition.onend = () => {
      isRecording = false;
      if (btnMic && !btnMic.classList.contains('processing')) {
        resetearEstadoMicrofono();
      }
    };
  } else {
    console.warn('[SPEECH] Web SpeechRecognition no soportado en este navegador.');
    if (statusTag) {
      statusTag.textContent = 'Voz no disponible';
      statusTag.className = 'status-indicator-tag';
    }
    if (statusDesc) statusDesc.textContent = 'Tu navegador no soporta voz nativa. Usa el campo de texto abajo.';
    if (btnMic) btnMic.style.opacity = '0.5';
  }

  function toggleGrabacion() {
    if (!recognition) {
      alert('Tu navegador no soporta reconocimiento de voz. Puedes usar el campo de texto en el cuadro central.');
      return;
    }

    if (isRecording) {
      recognition.stop();
    } else {
      if ('speechSynthesis' in window) {
        window.speechSynthesis.cancel();
      }
      try {
        recognition.start();
      } catch (err) {
        console.error('Error al iniciar reconocimiento:', err);
      }
    }
  }

  if (btnMic) btnMic.addEventListener('click', toggleGrabacion);

  function resetearEstadoMicrofono() {
    if (btnMic) btnMic.classList.remove('recording', 'processing');
    if (soundWave) soundWave.classList.remove('active');
    if (statusTag) {
      statusTag.className = 'status-indicator-tag';
      statusTag.textContent = 'Listo para escuchar';
    }
    if (statusDesc) statusDesc.textContent = 'Presiona el micrófono abajo para hablar o escribe tu antojo.';
    if (micCaptionText) micCaptionText.textContent = '🎙️ Toca para Hablar';
  }

  function setEstadoProcesando() {
    if (btnMic) {
      btnMic.classList.remove('recording');
      btnMic.classList.add('processing');
    }
    if (soundWave) soundWave.classList.add('active');
    if (statusTag) {
      statusTag.className = 'status-indicator-tag thinking';
      statusTag.textContent = 'Consultando stock e IA...';
    }
    if (statusDesc) statusDesc.textContent = 'Verificando inventario en SQLite en tiempo real...';
    if (micCaptionText) micCaptionText.textContent = '⚡ Procesando...';
  }

  // Síntesis de voz
  function cargarVoces() {
    if (!('speechSynthesis' in window)) return;
    const voces = window.speechSynthesis.getVoices();
    spanishVoice = voces.find(v => v.lang === 'es-CL') ||
                   voces.find(v => v.lang === 'es-ES') ||
                   voces.find(v => v.lang.startsWith('es')) ||
                   voces[0];
  }

  if ('speechSynthesis' in window) {
    cargarVoces();
    window.speechSynthesis.onvoiceschanged = cargarVoces;
  }

  function vocalizarTexto(texto) {
    if (voiceMuted || !('speechSynthesis' in window) || !texto) return;
    window.speechSynthesis.cancel();

    const utterance = new SpeechSynthesisUtterance(texto);
    if (spanishVoice) utterance.voice = spanishVoice;
    utterance.lang = spanishVoice ? spanishVoice.lang : 'es-CL';
    utterance.rate = 1.05;
    utterance.pitch = 1.0;

    utterance.onstart = () => {
      if (soundWave) soundWave.classList.add('active');
      if (statusTag) {
        statusTag.className = 'status-indicator-tag';
        statusTag.textContent = 'IA Respondiendo...';
      }
    };

    utterance.onend = () => {
      if (soundWave) soundWave.classList.remove('active');
      resetearEstadoMicrofono();
    };

    utterance.onerror = () => {
      if (soundWave) soundWave.classList.remove('active');
      resetearEstadoMicrofono();
    };

    window.speechSynthesis.speak(utterance);
  }

  if (btnToggleVoice) {
    btnToggleVoice.addEventListener('click', () => {
      voiceMuted = !voiceMuted;
      if (voiceMuted) {
        if ('speechSynthesis' in window) window.speechSynthesis.cancel();
        if (voiceIcon) voiceIcon.textContent = '🔇';
        if (voiceLabel) voiceLabel.textContent = 'Silenciado';
        btnToggleVoice.style.opacity = '0.7';
      } else {
        if (voiceIcon) voiceIcon.textContent = '🔊';
        if (voiceLabel) voiceLabel.textContent = 'Voz Activa';
        btnToggleVoice.style.opacity = '1';
      }
    });
  }

  // =========================================================
  // 5. PROCESAMIENTO DE MENSAJES Y PEDIDOS CON IA
  // =========================================================
  async function procesarMensajeUsuario(texto) {
    if (!texto || !texto.trim()) return;

    if (aiResponseText) {
      aiResponseText.textContent = `Escuché: "${texto.trim()}". Consultando disponibilidad...`;
    }
    setEstadoProcesando();

    try {
      const response = await fetch('/api/chat-pedido', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          mensaje: texto.trim(),
          session_id: sessionId,
        }),
      });

      if (!response.ok) {
        throw new Error(`Error en servidor: ${response.status}`);
      }

      const data = await response.json();
      console.log('[API RESPUESTA]', data);

      if (aiResponseText) {
        aiResponseText.textContent = data.respuesta_texto;
      }

      // Mostrar productos sugeridos por la IA en pantalla
      if (data.productos_ofrecidos && data.productos_ofrecidos.length > 0) {
        productosOfrecidosActuales = data.productos_ofrecidos;
        renderizarProductosOfrecidos(productosOfrecidosActuales);
      }

      // Actualizar pedido y estado del carrito
      renderizarPedido(data.pedido_actual);

      // Actualizar catálogo
      cargarInventarioEnVivo();

      // Vocalizar respuesta
      vocalizarTexto(data.respuesta_texto);

      // Si la IA detecta solicitud de pago, abrir la Pantalla de Pago CLIFF
      if (data.mostrar_pago) {
        setTimeout(() => {
          abrirPantallaPago(data.pedido_actual);
        }, 700);
      }

    } catch (error) {
      console.error('Error al procesar pedido:', error);
      const errorMsg = 'Lo siento, hubo un problema al procesar tu solicitud. Intenta nuevamente.';
      if (aiResponseText) {
        aiResponseText.textContent = errorMsg;
      }
      vocalizarTexto(errorMsg);
      resetearEstadoMicrofono();
    }
  }

  // Formulario de texto en el cuadro central
  if (chatForm) {
    chatForm.addEventListener('submit', (e) => {
      e.preventDefault();
      const texto = userTextInput.value.trim();
      if (texto) {
        procesarMensajeUsuario(texto);
        userTextInput.value = '';
      }
    });
  }

  // Chips de sugerencia rápida
  document.querySelectorAll('.chip-btn').forEach((chip) => {
    chip.addEventListener('click', () => {
      const texto = chip.getAttribute('data-text');
      if (texto) {
        procesarMensajeUsuario(texto);
      }
    });
  });

  // Botón para cerrar sección de ofrecidos
  if (btnCleanOffered && aiOfferedSection) {
    btnCleanOffered.addEventListener('click', () => {
      aiOfferedSection.style.display = 'none';
      productosOfrecidosActuales = [];
      if (aiEmptyPrompt) aiEmptyPrompt.style.display = 'flex';
    });
  }

  // =========================================================
  // 7. RENDERIZADO DE PRODUCTOS OFRECIDOS POR LA IA
  // =========================================================
  function renderizarProductosOfrecidos(productos) {
    if (!aiOfferedSection || !aiCardsGrid) return;
    if (aiEmptyPrompt) aiEmptyPrompt.style.display = 'none';
    aiCardsGrid.innerHTML = '';

    productos.forEach((prod) => {
      const isOut = prod.stock_disponible <= 0;
      const esBase = (prod.tipo_personalizado === 'base') || (prod.categoria === 'Panes');
      const esIngrediente = (prod.tipo_personalizado === 'ingrediente');
      const esCustomSandwich = prod.id === 9999 || prod.id === 31 || (prod.nombre && prod.nombre.toLowerCase().includes('sandwich personalizado')) || prod.es_combo_o_custom;

      const card = document.createElement('div');
      card.className = `ai-product-card ${isOut ? 'card-out' : ''} ${esCustomSandwich ? 'card-custom' : ''} ${esBase ? 'card-base' : ''}`;
      card.setAttribute('data-id', prod.id || '');
      card.setAttribute('data-nombre', prod.nombre || '');

      const imgUrl = prod.imagen_url || '';
      const fallbackEmoji = esBase ? '🥖' : (esIngrediente ? '🥗' : '🍽️');
      const imgHtml = imgUrl
        ? `<div class="card-img-wrapper">
             <img src="${escapeHtml(imgUrl)}" alt="${escapeHtml(prod.nombre)}" loading="lazy" onerror="this.parentElement.innerHTML='<div class=\\'card-img-fallback\\'>${fallbackEmoji}</div>'" />
             ${esCustomSandwich ? '<span class="card-tag-custom">Custom</span>' : (esBase ? '<span class="card-tag-custom" style="background:#f59e0b;color:#0f172a;">Paso 1: Pan</span>' : '')}
           </div>`
        : `<div class="card-img-wrapper"><div class="card-img-fallback">${fallbackEmoji}</div></div>`;

      const stockBadge = isOut
        ? '<span class="card-stock-tag stock-out">🚫 Agotado</span>'
        : `<span class="card-stock-tag stock-ok">✓ ${prod.stock_disponible} disp.</span>`;

      let badgeCatHtml = `<span class="card-cat-badge">${escapeHtml(prod.categoria || 'Menú')}</span>`;
      if (esBase) {
        badgeCatHtml = `<span class="card-cat-badge badge-role-base">🥖 Base / Pan</span>`;
      } else if (esIngrediente) {
        badgeCatHtml = `<span class="card-cat-badge badge-role-ingrediente">🥗 Ingrediente</span>`;
      }

      // Badges dietéticos
      let dietBadgeHtml = '';
      if (prod.es_vegano) {
        dietBadgeHtml = '<span class="card-diet-badge badge-vegano">🌿 Vegano</span>';
      } else if (prod.es_vegetariano) {
        dietBadgeHtml = '<span class="card-diet-badge badge-vegetariano">🌱 Veg</span>';
      }

      // Limpiar descripción redundante si solo repite la categoría y precio
      let descTexto = prod.descripcion || '';
      if (!descTexto || descTexto.includes('•') || (prod.categoria && descTexto.toLowerCase().startsWith(prod.categoria.toLowerCase()))) {
        descTexto = DESCRIPCIONES_CLIFF[prod.nombre] || '';
      }

      let btnAddText = '+ Agregar';
      if (isOut) {
        btnAddText = 'Agotado';
      } else if (esBase) {
        btnAddText = '🥖 Elegir este Pan';
      } else if (esIngrediente) {
        btnAddText = '+ Añadir a Sandwich';
      } else if (esCustomSandwich) {
        btnAddText = '🥪 Armar en Pantalla';
      }

      card.innerHTML = `
        ${imgHtml}
        <div class="card-body">
          <div class="card-title-header">
            <h4 class="card-title" title="${escapeHtml(prod.nombre)}">${escapeHtml(prod.nombre)}</h4>
          </div>
          ${descTexto ? `<p class="card-desc">${escapeHtml(descTexto)}</p>` : ''}
          <div class="card-meta-row">
            ${badgeCatHtml}
            ${dietBadgeHtml}
            ${stockBadge}
          </div>
          <div class="card-footer">
            <span class="card-price">${formatearMoneda(prod.precio)}</span>
            <button type="button" class="btn-card-add ${isOut ? 'disabled' : ''}" ${isOut ? 'disabled' : ''}>
              ${btnAddText}
            </button>
          </div>
        </div>
      `;

      const btnAdd = card.querySelector('.btn-card-add');
      if (btnAdd && !isOut) {
        btnAdd.addEventListener('click', () => {
          const originalHtml = btnAdd.innerHTML;
          btnAdd.classList.add('added-feedback');
          btnAdd.innerHTML = '<span>✓</span><span>¡Seleccionado!</span>';
          setTimeout(() => {
            btnAdd.classList.remove('added-feedback');
            if (btnAdd.textContent !== 'Agotado') {
              btnAdd.innerHTML = originalHtml;
            }
          }, 1200);

          if (esBase) {
            // Indicar a la IA la base de pan escogida
            procesarMensajeUsuario(prod.nombre);
          } else if (esIngrediente) {
            // Indicar a la IA el ingrediente escogido
            procesarMensajeUsuario(`Quiero agregar ${prod.nombre}`);
          } else if (esCustomSandwich) {
            abrirModalArmarSandwich();
          } else if (prod.es_combo_o_custom && prod.ingredientes_sugeridos && prod.ingredientes_sugeridos.length > 0) {
            procesarMensajeUsuario(`Arma un sandwich con ${prod.ingredientes_sugeridos.join(', ')}`);
          } else if (prod.id && prod.id > 0 && prod.id !== 9999) {
            agregarProductoDirecto(prod.id, btnAdd);
          } else {
            procesarMensajeUsuario(`Agrega un ${prod.nombre}`);
          }
        });
      }

      aiCardsGrid.appendChild(card);
    });

    aiOfferedSection.style.display = 'flex';
  }

  function actualizarStockEnTarjetasOfrecidas(productosList) {
    if (!aiCardsGrid || !productosList) return;
    const cards = aiCardsGrid.querySelectorAll('.ai-product-card');
    if (!cards || cards.length === 0) return;

    cards.forEach((card) => {
      const prodId = parseInt(card.getAttribute('data-id'), 10);
      const prodNombre = card.getAttribute('data-nombre') || '';
      const esCustom = card.classList.contains('card-custom');
      if (esCustom) return;

      let prodActualizado = null;
      if (prodId && prodId > 0 && prodId !== 9999) {
        prodActualizado = productosList.find((p) => p.id === prodId);
      } else if (prodNombre) {
        prodActualizado = productosList.find((p) => p.nombre.toLowerCase() === prodNombre.toLowerCase());
      }

      if (prodActualizado) {
        const isInactive = prodActualizado.activo === false;
        const isOut = isInactive || prodActualizado.stock_disponible <= 0;
        const stockTag = card.querySelector('.card-stock-tag');
        const btnAdd = card.querySelector('.btn-card-add');

        if (stockTag) {
          stockTag.className = `card-stock-tag ${isOut ? 'stock-out' : 'stock-ok'}`;
          stockTag.textContent = isInactive ? '🚫 No disponible' : (isOut ? '🚫 Agotado' : `✓ ${prodActualizado.stock_disponible} disp.`);
        }

        if (isOut) {
          card.classList.add('card-out');
          if (btnAdd) {
            btnAdd.disabled = true;
            btnAdd.classList.add('disabled');
            btnAdd.textContent = isInactive ? 'No disponible' : 'Agotado';
          }
        } else {
          card.classList.remove('card-out');
          if (btnAdd && btnAdd.classList.contains('disabled')) {
            btnAdd.disabled = false;
            btnAdd.classList.remove('disabled');
            btnAdd.textContent = '+ Agregar';
          }
        }
      }
    });
  }

  // =========================================================
  // 8. RENDERIZADO DEL CARRITO Y AJUSTES DE CANTIDAD
  // =========================================================
  function formatearMoneda(monto) {
    return new Intl.NumberFormat('es-CL', {
      style: 'currency',
      currency: 'CLP',
      maximumFractionDigits: 0,
    }).format(monto || 0);
  }

  function renderizarPedido(pedido) {
    ultimoPedidoEnMemoria = pedido || { items: [], total: 0 };
    const totalUnidades = (pedido && pedido.items) 
      ? pedido.items.reduce((acc, item) => acc + item.cantidad, 0) 
      : 0;
    const totalDinero = (pedido && pedido.total) ? pedido.total : 0;
    const totalFormateado = formatearMoneda(totalDinero);

    // Actualizar Badges del botón Carrito Gigante (Imagen 2)
    if (aiCartCountBadge) aiCartCountBadge.textContent = totalUnidades;
    if (aiCartTotalBadge) aiCartTotalBadge.textContent = totalFormateado;

    // Actualizar Badges del Carrito en Menú Tradicional
    if (menuCartCountBadge) menuCartCountBadge.textContent = totalUnidades;
    if (menuCartTotalBadge) menuCartTotalBadge.textContent = totalFormateado;

    // Actualizar Resumen en el Cajón Lateral (Drawer)
    if (summaryTotalItems) summaryTotalItems.textContent = `${totalUnidades} unid.`;
    if (summaryTotalAmount) summaryTotalAmount.textContent = totalFormateado;
    if (btnConfirmarPedido) btnConfirmarPedido.disabled = (totalUnidades === 0);

    if (!orderTbody) return;

    if (!pedido || !pedido.items || pedido.items.length === 0) {
      orderTbody.innerHTML = `
        <tr class="empty-order-row">
          <td colspan="4">
            <div class="empty-order-state">
              <span class="empty-icon">🛒</span>
              <p>Aún no hay productos en tu pedido.</p>
              <small>Usa la voz con la IA o explora el Menú tradicional.</small>
            </div>
          </td>
        </tr>
      `;
      return;
    }

    orderTbody.innerHTML = '';
    pedido.items.forEach((item) => {
      const detalleIngredientes = item.descripcion_adicional 
        ? `<div class="item-custom-ingredients">🥪 ${escapeHtml(item.descripcion_adicional)}</div>` 
        : '';

      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>
          <strong>${escapeHtml(item.nombre)}</strong>
          <span class="item-badge-cat">${escapeHtml(item.categoria || '')}</span>
          ${detalleIngredientes}
        </td>
        <td class="td-qty">
          <div class="qty-controls-wrap">
            <button class="btn-qty btn-minus" title="Restar 1">-</button>
            <span class="qty-val">${item.cantidad}</span>
            <button class="btn-qty btn-plus" title="Sumar 1">+</button>
          </div>
        </td>
        <td class="td-unit">${formatearMoneda(item.precio_unitario)}</td>
        <td class="td-sub">
          <span>${formatearMoneda(item.subtotal)}</span>
          <button class="btn-item-del" title="Eliminar del pedido">🗑️</button>
        </td>
      `;

      // Eventos de ajuste de cantidad
      const btnMinus = tr.querySelector('.btn-minus');
      const btnPlus = tr.querySelector('.btn-plus');
      const btnDel = tr.querySelector('.btn-item-del');

      if (btnMinus) btnMinus.addEventListener('click', () => ajustarItem(item.id, -1));
      if (btnPlus) btnPlus.addEventListener('click', () => ajustarItem(item.id, 1));
      if (btnDel) btnDel.addEventListener('click', () => ajustarItem(item.id, 0));

      orderTbody.appendChild(tr);
    });
  }

  // Ajustar cantidad de un ítem (+1, -1, 0)
  async function ajustarItem(detalleId, delta) {
    try {
      const res = await fetch(`/api/pedido/${sessionId}/ajustar-item`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ detalle_id: detalleId, delta: delta }),
      });

      if (!res.ok) {
        const errorData = await res.json();
        alert(errorData.detail || 'No se pudo modificar el ítem.');
        return;
      }

      const pedidoActualizado = await res.json();
      renderizarPedido(pedidoActualizado);
      cargarInventarioEnVivo();
    } catch (e) {
      console.error('Error al ajustar ítem:', e);
    }
  }

  // Adición directa al pedido sin pasar por LLM
  async function agregarProductoDirecto(productoId, btnElement) {
    try {
      const res = await fetch(`/api/pedido/${sessionId}/agregar-directo`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ producto_id: productoId, cantidad: 1 }),
      });

      if (!res.ok) {
        const errorData = await res.json();
        alert(errorData.detail || 'No se pudo agregar el producto.');
        return;
      }

      const pedidoActualizado = await res.json();
      renderizarPedido(pedidoActualizado);
      cargarInventarioEnVivo();

      if (btnElement) {
        const origText = btnElement.innerHTML;
        btnElement.classList.add('added-feedback');
        btnElement.innerHTML = '<span>✓</span><span>¡Añadido!</span>';
        setTimeout(() => {
          btnElement.classList.remove('added-feedback');
          btnElement.innerHTML = origText;
        }, 1100);
      }
    } catch (e) {
      console.error('Error al agregar producto directo:', e);
    }
  }

  // =========================================================
  // 8.5. PANTALLA DE PAGO CLIFF (CHECKOUT / MÉTODOS DE PAGO)
  // =========================================================
  function renderizarDetallePantallaPago(pedido) {
    if (!pagoItemsList || !pagoTotalAmount) return;
    pagoItemsList.innerHTML = '';
    const totalUnidades = (pedido && pedido.items) ? pedido.items.reduce((acc, i) => acc + i.cantidad, 0) : 0;
    const totalMonto = (pedido && pedido.total) ? pedido.total : 0;

    if (pagoItemsCount) {
      pagoItemsCount.textContent = `${totalUnidades} ${totalUnidades === 1 ? 'producto' : 'productos'}`;
    }
    pagoTotalAmount.textContent = formatearMoneda(totalMonto);

    if (!pedido || !pedido.items || pedido.items.length === 0) {
      pagoItemsList.innerHTML = `
        <div class="pago-item-row empty-pago-row">
          <span class="pago-item-name">No tienes productos agregados todavía.</span>
          <span class="pago-item-price">$0 CLP</span>
        </div>
      `;
      if (btnFinalizarPagoAhora) btnFinalizarPagoAhora.disabled = true;
      return;
    }

    if (btnFinalizarPagoAhora) btnFinalizarPagoAhora.disabled = false;

    pedido.items.forEach((item) => {
      const row = document.createElement('div');
      row.className = 'pago-item-row';
      const desc = item.descripcion_adicional ? `<br><small class="pago-item-sub">🥪 ${escapeHtml(item.descripcion_adicional)}</small>` : '';
      row.innerHTML = `
        <div class="pago-item-left">
          <span class="pago-item-qty">${item.cantidad}x</span>
          <span class="pago-item-name"><strong>${escapeHtml(item.nombre)}</strong>${desc}</span>
        </div>
        <span class="pago-item-price">${formatearMoneda(item.subtotal)}</span>
      `;
      pagoItemsList.appendChild(row);
    });
  }

  function abrirPantallaPago(pedidoOpcional) {
    cerrarCarrito();
    if (modalCustomSandwich) modalCustomSandwich.style.display = 'none';

    const p = pedidoOpcional || ultimoPedidoEnMemoria;
    if (p && p.items && p.items.length > 0) {
      renderizarDetallePantallaPago(p);
    } else {
      fetch(`/api/pedido/${sessionId}`)
        .then((r) => r.json())
        .then((data) => {
          ultimoPedidoEnMemoria = data;
          renderizarDetallePantallaPago(data);
        })
        .catch(() => {});
    }

    if (modalPago) {
      modalPago.style.display = 'flex';
    }
  }

  function cerrarPantallaPago() {
    if (modalPago) modalPago.style.display = 'none';
  }

  // =========================================================
  // 9. CARTA TRADICIONAL CLIFF (ESTILO KIOSCO Y REFERENCIA)
  // =========================================================
  async function cargarCatalogoTotem() {
    if (!totemProductsGrid) return;
    try {
      const res = await fetch('/api/productos');
      if (!res.ok) throw new Error('Error al cargar catálogo');
      catalogoProductos = await res.json();
      renderizarProductosTotem();
    } catch (e) {
      console.error('Error en catálogo totem:', e);
      totemProductsGrid.innerHTML = '<div class="catalog-loading">Error al cargar la carta.</div>';
    }
  }

  function renderizarProductosTotem() {
    if (!totemProductsGrid) return;
    totemProductsGrid.innerHTML = '';

    // Si se selecciona la categoría especial "Sandwiches Custom", mostrar el hero banner
    if (categoriaSeleccionada === 'Sandwiches Custom') {
      const hero = document.createElement('div');
      hero.className = 'totem-custom-hero';
      hero.innerHTML = `
        <div class="hero-emoji">🥪</div>
        <h3>Arma tu Sandwich 100% Personalizado</h3>
        <p>Escoge primero tu base de pan fresco horneado y luego añade todos los ingredientes, proteínas, agregados y salsas a tu gusto.</p>
        <button type="button" class="btn-launch-builder" id="btn-totem-launch-builder">
          <span>🥖</span>
          <span>Comenzar a Armar (Elegir Pan Primero)</span>
        </button>
      `;
      const btnLaunch = hero.querySelector('#btn-totem-launch-builder');
      if (btnLaunch) {
        btnLaunch.addEventListener('click', () => abrirModalArmarSandwich());
      }
      totemProductsGrid.appendChild(hero);
    }

    const productosFiltrados = catalogoProductos.filter((p) => {
      if (p.activo === false) return false;
      if (categoriaSeleccionada === 'TODOS') return true;
      return p.categoria.toLowerCase() === categoriaSeleccionada.toLowerCase();
    });

    if (productosFiltrados.length === 0 && categoriaSeleccionada !== 'Sandwiches Custom') {
      totemProductsGrid.innerHTML = `
        <div class="catalog-loading" style="grid-column: 1 / -1; padding: 3rem;">
          No hay productos disponibles en esta categoría actualmente.
        </div>
      `;
      return;
    }

    productosFiltrados.forEach((prod) => {
      const isOut = prod.stock_disponible <= 0;
      const esBase = (prod.tipo_personalizado === 'base') || (prod.categoria === 'Panes');
      const esIngrediente = (prod.tipo_personalizado === 'ingrediente');
      const esCustomSandwich = prod.id === 9999 || prod.id === 31 || (prod.nombre && prod.nombre.toLowerCase().includes('sandwich personalizado')) || prod.categoria === 'Sandwiches Custom';

      const card = document.createElement('div');
      card.className = `totem-item-card ${isOut ? 'card-out' : ''} ${esCustomSandwich ? 'card-custom' : ''}`;

      const fallbackEmoji = esBase ? '🥖' : (esIngrediente ? '🥗' : (esCustomSandwich ? '🥪' : '🍽️'));
      const imgHtml = prod.imagen_url
        ? `<div class="totem-item-thumb">
             <img src="${escapeHtml(prod.imagen_url)}" alt="${escapeHtml(prod.nombre)}" loading="lazy" onerror="this.parentElement.innerHTML='<div class=\\'totem-item-fallback\\'>${fallbackEmoji}</div>'" />
           </div>`
        : `<div class="totem-item-thumb"><div class="totem-item-fallback">${fallbackEmoji}</div></div>`;

      const stockBadge = isOut
        ? '<span class="card-stock-tag stock-out">🚫 Agotado</span>'
        : `<span class="card-stock-tag stock-ok">✓ ${prod.stock_disponible} disp.</span>`;

      let catBadgeHtml = `<span class="totem-item-cat">${escapeHtml(prod.categoria)}</span>`;
      if (esBase) {
        catBadgeHtml = `<span class="totem-item-cat badge-role-base">🥖 Base / Pan</span>`;
      } else if (esIngrediente) {
        catBadgeHtml = `<span class="totem-item-cat badge-role-ingrediente">🥗 Ingrediente</span>`;
      }

      let dietBadgeTotem = '';
      if (prod.es_vegano) {
        dietBadgeTotem = '<span class="badge-diet-vegano" style="font-size:0.7rem;padding:0.15rem 0.45rem;border-radius:12px;display:inline-flex;align-items:center;">🌿 Vegano</span>';
      } else if (prod.es_vegetariano) {
        dietBadgeTotem = '<span class="badge-diet-vegetariano" style="font-size:0.7rem;padding:0.15rem 0.45rem;border-radius:12px;display:inline-flex;align-items:center;">🌱 Veg</span>';
      }

      let btnText = '+ Agregar';
      if (isOut) {
        btnText = 'Agotado';
      } else if (esCustomSandwich) {
        btnText = '🥪 Armar Sandwich';
      } else if (esBase) {
        btnText = '🥪 Armar con este Pan';
      }

      const descTexto = prod.descripcion || DESCRIPCIONES_CLIFF[prod.nombre] || '';
      const esSandwich = (prod.categoria === 'Sandwiches' || prod.categoria === 'Comidas' || esCustomSandwich);

      card.innerHTML = `
        ${imgHtml}
        <div class="totem-item-body">
          <div class="totem-item-main">
            <h4 class="totem-item-title">${escapeHtml(prod.nombre)}</h4>
            ${descTexto ? `<p class="totem-item-desc">${escapeHtml(descTexto)}</p>` : ''}
            <div class="totem-item-badges">
              ${catBadgeHtml}
              ${dietBadgeTotem}
              ${stockBadge}
            </div>
          </div>
          <div class="totem-item-side">
            <div class="totem-price-breakdown">
              <div class="price-line-normal">
                <span class="price-label">Normal</span>
                <strong class="price-amount">${formatearMoneda(prod.precio)}</strong>
              </div>
              ${esSandwich ? `
              <div class="price-line-combo">
                <span class="price-sublabel">+ papa</span>
                <span class="price-subamount">${formatearMoneda(prod.precio + 1300)}</span>
              </div>` : ''}
            </div>
            <button type="button" class="btn-totem-add ${isOut ? 'disabled' : ''}" ${isOut ? 'disabled' : ''}>
              ${btnText}
            </button>
          </div>
        </div>
      `;

      const btnAdd = card.querySelector('.btn-totem-add');
      if (btnAdd && !isOut) {
        btnAdd.addEventListener('click', () => {
          if (esCustomSandwich) {
            abrirModalArmarSandwich();
          } else if (esBase) {
            // Abrir armador con esta base pre-seleccionada
            abrirModalArmarSandwich(prod.id);
          } else {
            agregarProductoDirecto(prod.id, btnAdd);
          }
        });
      }

      totemProductsGrid.appendChild(card);
    });
  }

  // Filtrado por pestañas de categoría (Estilo sidebar de referencia)
  categoryTabs.forEach((tab) => {
    tab.addEventListener('click', () => {
      categoryTabs.forEach((t) => t.classList.remove('active'));
      tab.classList.add('active');
      categoriaSeleccionada = tab.getAttribute('data-categoria') || 'TODOS';
      if (cliffCategoryHeading) {
        cliffCategoryHeading.textContent = `— ${categoriaSeleccionada === 'TODOS' ? 'Todos los Productos' : categoriaSeleccionada}`;
      }
      renderizarProductosTotem();
    });
  });

  // =========================================================
  // 9.5. ARMADOR DE SANDWICH PERSONALIZADO (PASO A PASO)
  // Regla estricta: Paso 1 (Pan Obligatorio) antes de Paso 2 (Ingredientes)
  // =========================================================
  async function abrirModalArmarSandwich(preselectedBaseId = null) {
    if (!modalCustomSandwich) return;
    modalCustomSandwich.style.display = 'flex';

    // Resetear selecciones
    builderSelectedBase = null;
    builderSelectedIngredients.clear();

    // Estado inicial: Paso 1 activo, Paso 2 bloqueado
    if (stepInd1) stepInd1.className = 'builder-step active';
    if (stepInd2) stepInd2.className = 'builder-step locked';
    if (step2Subtitle) step2Subtitle.textContent = 'Desbloqueable al elegir pan';
    if (sectionStepIngredients) sectionStepIngredients.classList.add('builder-section-locked');
    if (builderLockedOverlay) builderLockedOverlay.style.display = 'flex';

    if (baseStatusBadge) {
      baseStatusBadge.className = 'section-status-badge required';
      baseStatusBadge.textContent = 'Selección obligatoria';
    }
    if (ingredientsCountBadge) ingredientsCountBadge.textContent = '0 seleccionados';
    if (builderSelectedBaseName) builderSelectedBaseName.textContent = 'Ninguno seleccionado aún';
    if (builderSelectedIngredientsSummary) builderSelectedIngredientsSummary.textContent = '0 adicionales';
    if (builderTotalPrice) builderTotalPrice.textContent = formatearMoneda(0);
    if (btnBuilderConfirm) {
      btnBuilderConfirm.disabled = true;
      btnBuilderConfirm.innerHTML = '<span>🥪</span><span>Agregar al Pedido</span>';
    }

    if (builderBasesGrid) {
      builderBasesGrid.innerHTML = '<div class="catalog-loading">Cargando opciones de pan fresco...</div>';
    }
    if (builderIngredientsGrid) {
      builderIngredientsGrid.innerHTML = '';
    }

    try {
      const res = await fetch('/api/ingredientes');
      if (!res.ok) throw new Error('Error al cargar opciones de sandwich');
      const data = await res.json();
      builderBases = data.bases || [];
      builderIngredients = data.ingredientes || [];

      renderizarBasesBuilder();

      // Si se especificó una base previa (ej. clickeada desde menú de Panes)
      if (preselectedBaseId) {
        const found = builderBases.find((b) => b.id === preselectedBaseId && b.stock_disponible > 0 && b.activo !== false);
        if (found) {
          seleccionarBaseBuilder(found);
        }
      }
    } catch (err) {
      console.error('Error al cargar datos para armar sandwich:', err);
      if (builderBasesGrid) {
        builderBasesGrid.innerHTML = '<div class="catalog-loading">Error al cargar opciones. Intenta de nuevo.</div>';
      }
    }
  }

  function cerrarModalArmarSandwich() {
    if (modalCustomSandwich) {
      modalCustomSandwich.style.display = 'none';
    }
  }

  function renderizarBasesBuilder() {
    if (!builderBasesGrid) return;
    builderBasesGrid.innerHTML = '';

    if (!builderBases || builderBases.length === 0) {
      builderBasesGrid.innerHTML = '<div class="catalog-loading">No hay opciones de pan registradas en la base de datos.</div>';
      return;
    }

    builderBases.forEach((base) => {
      const isOut = (base.stock_disponible <= 0) || (base.activo === false);
      const isSelected = builderSelectedBase && builderSelectedBase.id === base.id;

      const card = document.createElement('div');
      card.className = `builder-card-item ${isOut ? 'out-of-stock' : ''} ${isSelected ? 'selected' : ''}`;
      card.setAttribute('data-id', base.id);

      const imgUrl = base.imagen_url || '';
      const imgHtml = imgUrl
        ? `<img src="${escapeHtml(imgUrl)}" alt="${escapeHtml(base.nombre)}" loading="lazy" onerror="this.parentElement.innerHTML='<div style=\\'display:flex;align-items:center;justify-content:center;height:100%;font-size:2.4rem;\\'>🥖</div>'" />`
        : `<div style="display:flex;align-items:center;justify-content:center;height:100%;font-size:2.4rem;">🥖</div>`;

      let dietBadgeBase = '';
      if (base.es_vegano) {
        dietBadgeBase = '<span class="badge-diet-vegano" style="font-size:0.68rem;padding:0.1rem 0.4rem;border-radius:10px;display:inline-flex;align-items:center;">🌿 Vegano</span>';
      } else if (base.es_vegetariano) {
        dietBadgeBase = '<span class="badge-diet-vegetariano" style="font-size:0.68rem;padding:0.1rem 0.4rem;border-radius:10px;display:inline-flex;align-items:center;">🌱 Veg</span>';
      }

      card.innerHTML = `
        <div class="builder-card-thumb">
          ${imgHtml}
          <span class="builder-card-selected-check">✓</span>
        </div>
        <div class="builder-card-info">
          <div style="display:flex;align-items:center;justify-content:space-between;gap:0.3rem;">
            <span class="builder-card-cat">${escapeHtml(base.categoria || 'Pan')} • Base</span>
            ${dietBadgeBase}
          </div>
          <h4 class="builder-card-title">${escapeHtml(base.nombre)}</h4>
          <div class="builder-card-bottom">
            <span class="builder-card-price">${formatearMoneda(base.precio)}</span>
            <span class="builder-card-stock">${isOut ? '🚫 Agotado' : `✓ ${base.stock_disponible} disp.`}</span>
          </div>
        </div>
      `;

      if (!isOut) {
        card.addEventListener('click', () => {
          seleccionarBaseBuilder(base);
        });
      }

      builderBasesGrid.appendChild(card);
    });
  }

  function seleccionarBaseBuilder(base) {
    if (!base || base.stock_disponible <= 0 || base.activo === false) return;

    builderSelectedBase = base;

    // Resaltar visualmente la tarjeta de la base seleccionada
    if (builderBasesGrid) {
      const cards = builderBasesGrid.querySelectorAll('.builder-card-item');
      cards.forEach((c) => {
        const cId = parseInt(c.getAttribute('data-id'), 10);
        if (cId === base.id) {
          c.classList.add('selected');
        } else {
          c.classList.remove('selected');
        }
      });
    }

    // Actualizar indicador del paso 1
    if (baseStatusBadge) {
      baseStatusBadge.className = 'section-status-badge selected';
      baseStatusBadge.textContent = `✓ Pan: ${base.nombre}`;
    }
    if (stepInd1) stepInd1.className = 'builder-step completed';
    if (stepInd2) stepInd2.className = 'builder-step active';
    if (step2Subtitle) step2Subtitle.textContent = '¡Desbloqueado! Elige tus ingredientes';

    // DESBLOQUEAR PASO 2 (INGREDIENTES)
    if (sectionStepIngredients) {
      sectionStepIngredients.classList.remove('builder-section-locked');
    }
    if (builderLockedOverlay) {
      builderLockedOverlay.style.display = 'none';
    }

    // Renderizar todos los ingredientes disponibles para selección
    renderizarIngredientesBuilder();

    // Actualizar resumen y precio total
    actualizarResumenBuilder();

    // Desplazamiento suave para guiar la atención al paso 2
    const scrollContent = document.querySelector('.builder-scroll-content');
    if (scrollContent && sectionStepIngredients) {
      const topOffset = sectionStepIngredients.offsetTop - scrollContent.offsetTop - 12;
      scrollContent.scrollTo({ top: Math.max(0, topOffset), behavior: 'smooth' });
    }
  }

  function renderizarIngredientesBuilder() {
    if (!builderIngredientsGrid) return;
    builderIngredientsGrid.innerHTML = '';

    if (!builderIngredients || builderIngredients.length === 0) {
      builderIngredientsGrid.innerHTML = '<div class="catalog-loading">No hay ingredientes registrados.</div>';
      return;
    }

    const categoryOrder = { 'Proteínas': 1, 'Agregados': 2, 'Salsas': 3 };
    const ordenados = [...builderIngredients].sort((a, b) => {
      const ordA = categoryOrder[a.categoria] || 99;
      const ordB = categoryOrder[b.categoria] || 99;
      if (ordA !== ordB) return ordA - ordB;
      return a.nombre.localeCompare(b.nombre);
    });

    ordenados.forEach((ing) => {
      const isOut = (ing.stock_disponible <= 0) || (ing.activo === false);
      const isSelected = builderSelectedIngredients.has(ing.id);

      const card = document.createElement('div');
      card.className = `builder-card-item ${isOut ? 'out-of-stock' : ''} ${isSelected ? 'selected' : ''}`;
      card.setAttribute('data-id', ing.id);

      const fallbackIcon = ing.categoria === 'Proteínas' ? '🥩' : (ing.categoria === 'Salsas' ? '🥫' : '🥑');
      const imgHtml = ing.imagen_url
        ? `<img src="${escapeHtml(ing.imagen_url)}" alt="${escapeHtml(ing.nombre)}" loading="lazy" onerror="this.parentElement.innerHTML='<div style=\\'display:flex;align-items:center;justify-content:center;height:100%;font-size:2rem;\\'>${fallbackIcon}</div>'" />`
        : `<div style="display:flex;align-items:center;justify-content:center;height:100%;font-size:2rem;">${fallbackIcon}</div>`;

      let dietBadgeIng = '';
      if (ing.es_vegano) {
        dietBadgeIng = '<span class="badge-diet-vegano" style="font-size:0.68rem;padding:0.1rem 0.4rem;border-radius:10px;display:inline-flex;align-items:center;">🌿 Vegano</span>';
      } else if (ing.es_vegetariano) {
        dietBadgeIng = '<span class="badge-diet-vegetariano" style="font-size:0.68rem;padding:0.1rem 0.4rem;border-radius:10px;display:inline-flex;align-items:center;">🌱 Veg</span>';
      }

      card.innerHTML = `
        <div class="builder-card-thumb">
          ${imgHtml}
          <span class="builder-card-selected-check">✓</span>
        </div>
        <div class="builder-card-info">
          <div style="display:flex;align-items:center;justify-content:space-between;gap:0.3rem;">
            <span class="builder-card-cat">${escapeHtml(ing.categoria || 'Ingrediente')}</span>
            ${dietBadgeIng}
          </div>
          <h4 class="builder-card-title">${escapeHtml(ing.nombre)}</h4>
          <div class="builder-card-bottom">
            <span class="builder-card-price">${formatearMoneda(ing.precio)}</span>
            <span class="builder-card-stock">${isOut ? '🚫 Agotado' : `✓ ${ing.stock_disponible} disp.`}</span>
          </div>
        </div>
      `;

      if (!isOut) {
        card.addEventListener('click', () => {
          toggleIngredienteBuilder(ing, card);
        });
      }

      builderIngredientsGrid.appendChild(card);
    });
  }

  function toggleIngredienteBuilder(ing, card) {
    if (!builderSelectedBase) {
      alert('Debes seleccionar primero el pan (base obligatoria) en el Paso 1.');
      return;
    }
    if (!ing || ing.stock_disponible <= 0 || ing.activo === false) return;

    if (builderSelectedIngredients.has(ing.id)) {
      builderSelectedIngredients.delete(ing.id);
      card.classList.remove('selected');
    } else {
      builderSelectedIngredients.set(ing.id, ing);
      card.classList.add('selected');
    }

    actualizarResumenBuilder();
  }

  function actualizarResumenBuilder() {
    const basePrice = builderSelectedBase ? builderSelectedBase.precio : 0;
    let ingredientsPrice = 0;
    const nombresIngs = [];

    builderSelectedIngredients.forEach((ing) => {
      ingredientsPrice += ing.precio;
      nombresIngs.push(ing.nombre);
    });

    const totalPrice = basePrice + ingredientsPrice;

    if (builderSelectedBaseName) {
      if (builderSelectedBase) {
        builderSelectedBaseName.innerHTML = `${escapeHtml(builderSelectedBase.nombre)} <span style="color:#f59e0b;font-weight:700;margin-left:6px;">(${formatearMoneda(builderSelectedBase.precio)})</span>`;
      } else {
        builderSelectedBaseName.textContent = 'Ninguno seleccionado aún';
      }
    }

    if (builderSelectedIngredientsSummary) {
      if (builderSelectedIngredients.size === 0) {
        builderSelectedIngredientsSummary.textContent = builderSelectedBase ? '0 adicionales (solo pan)' : '0 adicionales';
      } else {
        builderSelectedIngredientsSummary.textContent = `${builderSelectedIngredients.size} seleccionados: ${nombresIngs.join(', ')}`;
      }
    }

    if (ingredientsCountBadge) {
      ingredientsCountBadge.textContent = `${builderSelectedIngredients.size} seleccionados`;
    }

    if (builderTotalPrice) {
      builderTotalPrice.textContent = formatearMoneda(totalPrice);
    }

    if (btnBuilderConfirm) {
      btnBuilderConfirm.disabled = !builderSelectedBase;
    }
  }

  async function confirmarSandwichBuilder() {
    if (!builderSelectedBase) {
      alert('Es obligatorio escoger primero el pan (base) para tu sandwich.');
      return;
    }

    if (btnBuilderConfirm) {
      btnBuilderConfirm.disabled = true;
      btnBuilderConfirm.innerHTML = '<span>⏳</span><span>Agregando sandwich...</span>';
    }

    try {
      const res = await fetch(`/api/pedido/${sessionId}/armar-sandwich`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          base_id: builderSelectedBase.id,
          ingredientes_ids: Array.from(builderSelectedIngredients.keys()),
        }),
      });

      if (!res.ok) {
        const err = await res.json();
        alert(err.detail || 'No se pudo armar el sandwich.');
        if (btnBuilderConfirm) {
          btnBuilderConfirm.disabled = false;
          btnBuilderConfirm.innerHTML = '<span>🥪</span><span>Agregar al Pedido</span>';
        }
        return;
      }

      const pedidoActualizado = await res.json();
      renderizarPedido(pedidoActualizado);
      cargarInventarioEnVivo();
      cerrarModalArmarSandwich();

      const totalIngs = builderSelectedIngredients.size;
      const msg = `¡Sandwich personalizado agregado al pedido! Base: ${builderSelectedBase.nombre}, ${totalIngs} ingrediente${totalIngs === 1 ? '' : 's'}.`;
      if (aiResponseText) {
        aiResponseText.textContent = msg;
      }
      vocalizarTexto('Sandwich personalizado agregado a tu orden.');

      if (btnBuilderConfirm) {
        btnBuilderConfirm.innerHTML = '<span>🥪</span><span>Agregar al Pedido</span>';
        btnBuilderConfirm.disabled = false;
      }
    } catch (err) {
      console.error('Error al agregar sandwich armado:', err);
      alert('Ocurrió un error al enviar el sandwich al pedido. Intenta nuevamente.');
      if (btnBuilderConfirm) {
        btnBuilderConfirm.disabled = false;
        btnBuilderConfirm.innerHTML = '<span>🥪</span><span>Agregar al Pedido</span>';
      }
    }
  }

  // Event listeners del modal armador
  if (btnCloseCustomBuilder) {
    btnCloseCustomBuilder.addEventListener('click', cerrarModalArmarSandwich);
  }
  if (btnBuilderConfirm) {
    btnBuilderConfirm.addEventListener('click', confirmarSandwichBuilder);
  }
  if (modalCustomSandwich) {
    modalCustomSandwich.addEventListener('click', (e) => {
      if (e.target === modalCustomSandwich) {
        cerrarModalArmarSandwich();
      }
    });
  }

  // =========================================================
  // 10. MONITOR DE INVENTARIO E INGREDIENTES EN VIVO
  // =========================================================
  async function cargarIngredientesEnVivo() {
    const container = document.getElementById('ingredient-tags-grid');
    if (!container) return;
    try {
      const res = await fetch('/api/ingredientes');
      if (!res.ok) return;
      const agrupados = await res.json();

      container.innerHTML = '';
      Object.entries(agrupados).forEach(([categoria, lista]) => {
        if (categoria === 'bases' || categoria === 'ingredientes') return;
        if (!Array.isArray(lista)) return;
        lista.forEach((ing) => {
          const isOut = ing.stock_disponible <= 0;
          const badge = document.createElement('button');
          badge.type = 'button';
          badge.className = `ing-badge ${isOut ? 'ing-out' : ''}`;
          badge.title = isOut 
            ? `${ing.nombre} - AGOTADO (0)` 
            : `${ing.nombre} (${formatearMoneda(ing.precio)}) - Stock: ${ing.stock_disponible}`;
          badge.innerHTML = `
            <span>${escapeHtml(ing.nombre)}</span>
            <small style="opacity:0.75">${formatearMoneda(ing.precio)}</small>
            ${isOut ? '<span style="color:#f87171;font-weight:700">🚫</span>' : `<span style="color:#34d399;font-weight:700">✓${ing.stock_disponible}</span>`}
          `;
          if (!isOut) {
            badge.addEventListener('click', () => {
              if (userTextInput) {
                userTextInput.value = userTextInput.value 
                  ? `${userTextInput.value} + ${ing.nombre}` 
                  : `Arma un sandwich con ${ing.nombre}`;
                userTextInput.focus();
              }
            });
          }
          container.appendChild(badge);
        });
      });
    } catch (e) {
      console.error('Error al cargar ingredientes:', e);
    }
  }

  async function cargarInventarioEnVivo() {
    cargarIngredientesEnVivo();
    try {
      const res = await fetch('/api/productos');
      if (!res.ok) return;
      catalogoProductos = await res.json();
      actualizarStockEnTarjetasOfrecidas(catalogoProductos);
      if (viewTraditionalMenu && viewTraditionalMenu.classList.contains('active')) {
        renderizarProductosTotem();
      }
    } catch (e) {
      console.error('Error al sincronizar inventario:', e);
    }
  }

  // =========================================================
  // 11. ACCIONES: NUEVO PEDIDO Y CONFIRMACIÓN DE PAGO
  // =========================================================
  async function reiniciarPedido() {
    try {
      await fetch(`/api/nuevo-pedido/${sessionId}`, { method: 'POST' });
    } catch (e) {
      console.warn('Error al limpiar pedido en backend:', e);
    }

    sessionStorage.removeItem('kiosk_session_id');
    sessionId = getOrCreateSessionId();
    actualizarEtiquetasSesion();

    if (aiResponseText) {
      aiResponseText.textContent = '¡Nuevo pedido iniciado! Presiona el micrófono abajo para ordenar o elige una sugerencia.';
    }
    if (aiEmptyPrompt) aiEmptyPrompt.style.display = 'flex';
    if (aiOfferedSection) aiOfferedSection.style.display = 'none';

    renderizarPedido({ items: [], total: 0 });
    productosOfrecidosActuales = [];

    cargarInventarioEnVivo();
    resetearEstadoMicrofono();
  }

  if (btnNuevoPedido) {
    btnNuevoPedido.addEventListener('click', () => {
      if (confirm('¿Deseas reiniciar el pedido actual y comenzar uno nuevo?')) {
        reiniciarPedido();
      }
    });
  }

  // Confirmar y pagar desde el cajón lateral -> Abre la Pantalla de Pago CLIFF
  if (btnConfirmarPedido) {
    btnConfirmarPedido.addEventListener('click', () => {
      cerrarCarrito();
      abrirPantallaPago();
    });
  }

  // Cerrar Pantalla de Pago
  if (btnCerrarPago) {
    btnCerrarPago.addEventListener('click', () => {
      cerrarPantallaPago();
    });
  }
  if (btnCancelarPago) {
    btnCancelarPago.addEventListener('click', () => {
      cerrarPantallaPago();
    });
  }

  // Finalizar pago desde la Pantalla de Pago (habla la frase ecológica de CLIFF y finaliza)
  if (btnFinalizarPagoAhora) {
    btnFinalizarPagoAhora.addEventListener('click', async () => {
      // Frase exacta solicitada por el usuario
      const ecoPhrase = "Muchas gracias por comprar en Cliff, recuerda que nuestros envases son reciclables y ecológicos.";
      vocalizarTexto(ecoPhrase);

      cerrarPantallaPago();

      if (modalTotalBox && pagoTotalAmount) {
        modalTotalBox.textContent = pagoTotalAmount.textContent;
      }
      if (modalConfirmacion) {
        modalConfirmacion.style.display = 'flex';
      }

      try {
        await fetch(`/api/nuevo-pedido/${sessionId}`, { method: 'POST' });
      } catch (e) {
        console.warn('Error al marcar pedido completado en backend:', e);
      }
    });
  }

  if (btnCerrarModal) {
    btnCerrarModal.addEventListener('click', () => {
      if (modalConfirmacion) modalConfirmacion.style.display = 'none';
      reiniciarPedido();
      mostrarVista('welcome');
    });
  }

  // Botón flotante inferior derecho con lupa (navegar a Autoservicio IA)
  if (cliffFloatingSearchBtn) {
    cliffFloatingSearchBtn.addEventListener('click', () => {
      mostrarVista('ai');
    });
  }

  // Botones de Compartir (Welcome, AI, Carta)
  function compartirCLIFF() {
    if (navigator.share) {
      navigator.share({
        title: 'CLIFF - Sandwichería & Kiosco Autoservicio',
        text: '¡Pide los mejores sandwiches tradicionales en CLIFF!',
        url: window.location.href,
      }).catch(() => {});
    } else if (navigator.clipboard) {
      navigator.clipboard.writeText(window.location.href).then(() => {
        alert('¡Enlace de CLIFF copiado al portapapeles!');
      }).catch(() => {});
    }
  }

  if (btnShareWelcome) btnShareWelcome.addEventListener('click', compartirCLIFF);
  if (btnShareAi) btnShareAi.addEventListener('click', compartirCLIFF);
  if (btnShareMenu) btnShareMenu.addEventListener('click', compartirCLIFF);

  // Selección visual de métodos de pago en el modal
  document.querySelectorAll('input[name="metodo-pago"]').forEach((radio) => {
    radio.addEventListener('change', (e) => {
      document.querySelectorAll('.pago-method-card').forEach((c) => c.classList.remove('active'));
      const parentLabel = e.target.closest('.pago-method-card');
      if (parentLabel) parentLabel.classList.add('active');
    });
  });

  // =========================================================
  // 12. INICIALIZACIÓN
  // =========================================================
  function escapeHtml(text) {
    if (!text) return '';
    return text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  // Cargar estado inicial del pedido e inventario
  fetch(`/api/pedido/${sessionId}`)
    .then((r) => r.json())
    .then((data) => renderizarPedido(data))
    .catch(() => {});

  cargarInventarioEnVivo();

  // Por defecto, mostrar la pantalla de bienvenida (Imagen 1)
  mostrarVista('welcome');
});
