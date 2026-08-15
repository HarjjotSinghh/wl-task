import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';

// Brand story + More From carousel. Data comes from Liquid JSON, not a client fetch.

/** Locale strings sometimes include an arrow; the SVG is the actual icon. */
function stripArrow(value) {
  return String(value || '')
    .replace(/\s*[→➜➔⟶»›].*$/u, '')
    .trim();
}

/** Small stroke chevron for the carousel prev/next buttons. */
function NavChevron({ direction }) {
  const d = direction === 'left' ? 'M6.25 1.5 1.75 7l4.5 5.5' : 'M1.75 1.5 6.25 7l-4.5 5.5';
  return (
    <svg className="wl-vc__chevron" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8 14" fill="none" aria-hidden="true">
      <path d={d} stroke="currentColor" strokeWidth="1.55" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** Right arrow used on VIEW ALL and Add to Cart. */
function ArrowIcon({ strokeWidth = '2.6' }) {
  return (
    <svg
      className="wl-vc__arrow"
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <path
        d="M5 12h14M13 6l6 6-6 6"
        stroke="currentColor"
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** `750ml • 45% ABV` — omits the dot if either side is missing. */
function MetaLine({ size, abv }) {
  if (!size && !abv) return null;
  return (
    <p className="wl-vc__card-meta">
      {size ? <span>{size}</span> : null}
      {size && abv ? (
        <span className="wl-vc__dot" aria-hidden="true">
          •
        </span>
      ) : null}
      {abv ? <span>{abv}</span> : null}
    </p>
  );
}

/** Fill the `{{ count }} reviews` locale string. */
function reviewsLabel(count, template) {
  const n = Number(count) || 0;
  return template.replace('{{ count }}', String(n));
}

/** Ajax add that also refreshes Dawn's cart drawer / notification. */
async function addToCart(variantId) {
  const cart = document.querySelector('cart-notification') || document.querySelector('cart-drawer');
  const payload = { id: String(variantId), quantity: 1 };

  if (cart && typeof cart.getSectionsToRender === 'function') {
    payload.sections = cart.getSectionsToRender().map((section) => section.id);
    payload.sections_url = window.location.pathname;
    if (typeof cart.setActiveElement === 'function') {
      cart.setActiveElement(document.activeElement);
    }
  }

  const endpoint = (window.routes && window.routes.cart_add_url) || '/cart/add.js';
  const response = await fetch(endpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/javascript',
      'X-Requested-With': 'XMLHttpRequest',
    },
    body: JSON.stringify(payload),
  });

  const data = await response.json();
  if (data.status) {
    throw new Error(data.description || data.message || 'Could not add to cart');
  }

  if (typeof window.publish === 'function' && window.PUB_SUB_EVENTS) {
    window.publish(window.PUB_SUB_EVENTS.cartUpdate, {
      source: 'vendor-collection',
      productVariantId: variantId,
      cartData: data,
    });
  }

  if (cart && typeof cart.renderContents === 'function') {
    cart.renderContents(data);
  }

  return data;
}

/** One More From card: media, rating, title, meta, price, Add to Cart. */
function ProductCard({ product, labels, addingId, onAdd }) {
  const hasRating = product.rating != null && product.rating !== '';

  return (
    <article className="wl-vc__card">
      <a className="wl-vc__card-link" href={product.url}>
        <div className="wl-vc__card-media">
          {product.image ? (
            <img src={product.image} alt={product.imageAlt || product.title} width="234" height="234" />
          ) : null}
        </div>
        {hasRating ? (
          <p className="wl-vc__rating">
            <span className="wl-vc__star" aria-hidden="true" />
            <span className="wl-vc__rating-value">{product.rating}</span>
            <span className="wl-vc__rating-count">
              ({reviewsLabel(product.reviewCount, labels.reviews)})
            </span>
          </p>
        ) : null}
        <h3 className="wl-vc__card-title">{product.title}</h3>
        <MetaLine size={product.size} abv={product.abv} />
        <p className="wl-vc__prices">
          <span className={product.onSale ? 'wl-vc__price wl-vc__price--sale' : 'wl-vc__price'}>
            {product.price}
          </span>
          {product.onSale && product.compareAtPrice ? (
            <s className="wl-vc__compare">{product.compareAtPrice}</s>
          ) : null}
        </p>
      </a>
      <button
        className="wl-vc__atc"
        type="button"
        disabled={!product.available || addingId === product.variantId}
        onClick={() => onAdd(product)}
      >
        {addingId === product.variantId ? (
          labels.adding
        ) : (
          <>
            {stripArrow(labels.addToCart)}
            <ArrowIcon />
          </>
        )}
      </button>
    </article>
  );
}

/** Triple the list so native scroll can wrap without a visible jump. */
function loopProducts(products, copies = 3) {
  const items = [];
  for (let copy = 0; copy < copies; copy += 1) {
    products.forEach((product, index) => {
      items.push({ ...product, loopKey: `${copy}-${product.id}-${index}` });
    });
  }
  return items;
}

/** Distance from one card to the next, including gap. */
function cardStep(scroller) {
  const cards = scroller.querySelectorAll('.wl-vc__card');
  if (!cards.length) return 0;
  if (cards.length < 2) return cards[0].offsetWidth || 0;
  const step = cards[1].offsetLeft - cards[0].offsetLeft;
  return Math.abs(step) > 1 ? Math.abs(step) : cards[0].offsetWidth || 0;
}

/** MORE FROM row: infinite scroller, progress bar, arrows, Add to Cart. */
function MoreFrom({ collection, products, labels }) {
  const scrollerRef = useRef(null);
  const wrappingRef = useRef(false); // true while we jump the cloned track; ignore those scroll events
  const [thumb, setThumb] = useState({ width: 20, x: 0 });
  const [addingId, setAddingId] = useState(null);
  const [error, setError] = useState('');
  const count = products.length;
  const carouselProducts = useMemo(() => loopProducts(products), [products]);

  /** Pixel width of one full product set (used to wrap the cloned track). */
  const setWidth = useCallback(() => {
    const el = scrollerRef.current;
    if (!el || count === 0) return 0;
    const step = cardStep(el);
    if (step <= 0) return 0;
    return step * count;
  }, [count]);

  /** If scroll leaves the middle copy, jump by one set-width so looping feels endless. */
  const wrapIfNeeded = useCallback(() => {
    const el = scrollerRef.current;
    const width = setWidth();
    if (!el || width <= 0 || wrappingRef.current) return;
    if (el.scrollWidth <= el.clientWidth + 2) return;
    if (el.scrollLeft < width) {
      wrappingRef.current = true;
      el.scrollLeft += width;
      wrappingRef.current = false;
    } else if (el.scrollLeft >= width * 2 - 1) {
      wrappingRef.current = true;
      el.scrollLeft -= width;
      wrappingRef.current = false;
    }
  }, [setWidth]);

  /** Map scroll offset in one product-set to the gold progress thumb. */
  const sync = useCallback(() => {
    const el = scrollerRef.current;
    const width = setWidth();
    if (!el) return;
    if (width <= 0) {
      setThumb({ width: 20, x: 0 });
      return;
    }
    const offset = ((el.scrollLeft % width) + width) % width;
    const fill = 20 + (offset / width) * 80;
    setThumb({ width: fill, x: 0 });
  }, [setWidth]);

  /** Start (and stay) on the middle clone so prev and next both have room. */
  const jumpToMiddle = useCallback(() => {
    const el = scrollerRef.current;
    const width = setWidth();
    if (!el || width <= 0) return;
    const offset = ((el.scrollLeft % width) + width) % width;
    wrappingRef.current = true;
    el.scrollLeft = width + offset;
    wrappingRef.current = false;
    sync();
  }, [setWidth, sync]);

  useLayoutEffect(() => {
    jumpToMiddle();
  }, [jumpToMiddle, carouselProducts.length]);

  useEffect(() => {
    const el = scrollerRef.current;
    if (!el) return;

    const onScroll = () => {
      if (!wrappingRef.current) wrapIfNeeded();
      sync();
    };

    const images = el.querySelectorAll('img');
    images.forEach((img) => {
      if (!img.complete) img.addEventListener('load', jumpToMiddle);
    });
    el.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', jumpToMiddle);
    jumpToMiddle();
    return () => {
      images.forEach((img) => img.removeEventListener('load', jumpToMiddle));
      el.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', jumpToMiddle);
    };
  }, [jumpToMiddle, sync, wrapIfNeeded, carouselProducts.length]);

  /** Advance one card; keep the jump inside the middle clone. */
  const scrollByCard = (direction) => {
    const el = scrollerRef.current;
    if (!el) return;
    const step = cardStep(el);
    const width = step * count;
    if (step <= 0 || width <= 0) return;
    wrapIfNeeded();
    let next = el.scrollLeft + direction * step;
    if (next < width) next += width;
    if (next >= width * 2) next -= width;
    wrappingRef.current = true;
    el.scrollTo({ left: next, behavior: 'smooth' });
    window.setTimeout(() => {
      wrappingRef.current = false;
      wrapIfNeeded();
      sync();
    }, 400);
  };

  /** Disable the button while the Ajax add is in flight. */
  const onAdd = async (product) => {
    setError('');
    setAddingId(product.variantId);
    try {
      await addToCart(product.variantId);
    } catch (err) {
      setError(err.message || labels.addError);
    } finally {
      setAddingId(null);
    }
  };

  const heading = labels.moreFrom.includes('{{ title }}')
    ? labels.moreFrom.replace('{{ title }}', collection.titleUpper || collection.title)
    : labels.moreFrom;

  return (
    <div className="wl-vc__more">
      <div className="wl-vc__more-head">
        <h2 className="wl-vc__more-title">{heading}</h2>
        <a className="wl-vc__view-all" href={collection.url}>
          {stripArrow(labels.viewAll)}
          <ArrowIcon strokeWidth="2.15" />
        </a>
      </div>
      <div
        className="wl-vc__scroller"
        ref={scrollerRef}
        tabIndex="0"
        role="region"
        aria-label={heading}
      >
        {carouselProducts.map((product) => (
          <ProductCard
            key={product.loopKey}
            product={product}
            labels={labels}
            addingId={addingId}
            onAdd={onAdd}
          />
        ))}
      </div>
      {error ? <p className="wl-vc__error">{error}</p> : null}
      <div className="wl-vc__controls">
        <div className="wl-vc__progress" aria-hidden="true">
          <span
            className="wl-vc__progress-thumb"
            style={{ width: `${thumb.width}%` }}
          />
        </div>
        <div className="wl-vc__nav">
          <button
            className="wl-vc__nav-btn"
            type="button"
            aria-label={labels.prev}
            onClick={(event) => {
              event.preventDefault();
              scrollByCard(-1);
            }}
          >
            <NavChevron direction="left" />
          </button>
          <button
            className="wl-vc__nav-btn"
            type="button"
            aria-label={labels.next}
            onClick={(event) => {
              event.preventDefault();
              scrollByCard(1);
            }}
          >
            <NavChevron direction="right" />
          </button>
        </div>
      </div>
    </div>
  );
}

/** Brand story + optional More From. Image and description are omitted when missing. */
export function App({ data }) {
  const { collection, products, labels, showMoreFrom } = data;
  const hasImage = Boolean(collection.image);
  const hasDescription = Boolean(collection.descriptionHtml);
  const brandClass = useMemo(
    () => (hasImage ? 'wl-vc__brand wl-vc__brand--split' : 'wl-vc__brand wl-vc__brand--text'),
    [hasImage]
  );

  return (
    <div className="wl-vc">
      <div className="wl-vc__inner">
        <div className={brandClass}>
          {hasImage ? (
            <div className="wl-vc__media">
              <img src={collection.image} alt={collection.imageAlt || collection.title} />
            </div>
          ) : null}
          <div className="wl-vc__copy">
            <p className="wl-vc__kicker">
              <span>{labels.kicker}</span>
              <span className="wl-vc__kicker-line" />
            </p>
            <h2 className="wl-vc__title">{collection.title}</h2>
            {hasDescription ? (
              <div
                className="wl-vc__body"
                dangerouslySetInnerHTML={{ __html: collection.descriptionHtml }}
              />
            ) : null}
          </div>
        </div>
        {showMoreFrom && products.length > 0 ? (
          <MoreFrom collection={collection} products={products} labels={labels} />
        ) : null}
      </div>
    </div>
  );
}
