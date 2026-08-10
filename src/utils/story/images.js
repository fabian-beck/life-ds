/**
 * Event and portrait imagery: thumbnail URL derivation (Wikimedia, Flickr),
 * validity filtering, and source labeling.
 */
import { assetUrl } from "../assetUrl.js";

/**
 * Standard thumbnail widths allowed by Wikimedia for direct (hotlinked) requests.
 * Non-standard widths are rejected with HTTP 400, so any requested width must be
 * snapped to one of these. See https://www.mediawiki.org/wiki/Common_thumbnail_sizes
 */
const WIKIMEDIA_STANDARD_THUMB_WIDTHS = [
  20, 40, 60, 120, 250, 330, 500, 960, 1280, 1920, 3840,
];
/**
 * Snap a desired width up to the smallest allowed Wikimedia standard width
 * (capped at the largest), so the request is accepted and quality is sufficient.
 * @param {number} width - Desired width in pixels
 * @returns {number} A standard Wikimedia thumbnail width
 */
function snapToWikimediaWidth(width) {
  const sizes = WIKIMEDIA_STANDARD_THUMB_WIDTHS;
  return sizes.find((size) => size >= width) ?? sizes[sizes.length - 1];
}
const FLICKR_SIZE_SUFFIXES = [
  [100, "t"],
  [240, "m"],
  [320, "n"],
  [400, "w"],
  [500, ""],
  [640, "z"],
  [800, "c"],
  [1024, "b"],
];
/**
 * Build a Flickr image URL at the nearest supported public size.
 * Size suffixes larger than 1024px use per-size secrets, so they are not
 * safe to derive from a URL stored in the dataset.
 * @param {string} imageUrl - Flickr static image URL
 * @param {number} width - Desired longest edge in pixels
 * @returns {string} Optimized URL or the original when it cannot be derived
 */
function getFlickrThumbnailUrl(imageUrl, width) {
  const match = imageUrl.match(
    /^(https:\/\/live\.staticflickr\.com\/\d+\/\d+_[^_/.]+)(?:_([a-z0-9]+))?(\.(?:jpe?g|png|gif)(?:\?.*)?)$/i
  );
  if (!match) return imageUrl;

  const existingSuffix = match[2]?.toLowerCase();
  const publicSuffixes = ["s", "q", "t", "m", "n", "w", "z", "c", "b"];
  if (existingSuffix && !publicSuffixes.includes(existingSuffix)) {
    return imageUrl;
  }

  const suffix =
    FLICKR_SIZE_SUFFIXES.find(([size]) => size >= width)?.[1] ?? "b";
  return `${match[1]}${suffix ? `_${suffix}` : ""}${match[3]}`;
}
/**
 * Get optimized image URL based on desired width.
 * For portrait objects with multi-size WebP support, selects appropriate size.
 * For Wikimedia Commons and Flickr URLs, uses their thumbnail services.
 * For direct URLs, returns as-is.
 * @param {Object|string} imageOrPortrait - Portrait object or direct URL string
 * @param {number} width - Desired width in pixels
 * @returns {string} Optimized URL or original
 */
export function getThumbnailUrl(imageOrPortrait, width = 400) {
  // Handle portrait objects with multi-size WebP support
  if (imageOrPortrait && typeof imageOrPortrait === "object") {
    const portrait = imageOrPortrait;

    // Select appropriate size based on target width
    if (portrait.thumbnail || portrait.medium || portrait.full) {
      if (width <= 200 && portrait.thumbnail) {
        return assetUrl(portrait.thumbnail);
      } else if (width <= 400 && portrait.medium) {
        return assetUrl(portrait.medium);
      } else if (portrait.full) {
        return assetUrl(portrait.full);
      }
      // Fallback to any available size
      return assetUrl(portrait.thumbnail || portrait.medium || portrait.full);
    }

    // Legacy: portrait object has image property
    if (portrait.image) {
      imageOrPortrait = portrait.image;
    }
  }

  // From here on, imageOrPortrait should be a string URL
  const imageUrl = imageOrPortrait;
  if (!imageUrl || typeof imageUrl !== "string") return imageUrl;

  // Optimize Wikimedia Commons images
  if (imageUrl.includes("upload.wikimedia.org/wikipedia/commons/")) {
    // Wikimedia rejects non-standard thumbnail widths on direct requests (HTTP 400),
    // so snap to an allowed standard size.
    const stdWidth = snapToWikimediaWidth(width);

    // The Commons API hands its URLs back with `?utm_source=...` attached, and
    // a size is appended to the *path*: left on, the tracking ends up in the
    // middle of the address and the picture 404s. It carries nothing the
    // reader needs, so it goes.
    const cleanUrl = imageUrl.split("?")[0];

    // Check if URL is already a thumbnail
    if (cleanUrl.includes("/thumb/")) {
      // URL is already a thumbnail - just adjust the size
      // Example: .../thumb/a/b/File.svg/800px-File.svg.png -> .../thumb/a/b/File.svg/500px-File.svg.png
      return cleanUrl.replace(/\/\d+px-([^/]+)$/, `/${stdWidth}px-$1`);
    }

    // Convert full URL to thumbnail URL
    const parts = cleanUrl.split("/wikipedia/commons/");
    if (parts.length === 2) {
      const [base, path] = parts;
      const filename = path.split("/").pop();
      // For SVG files, append .png to get the rasterized version
      const thumbFilename = filename.toLowerCase().endsWith(".svg")
        ? `${filename}.png`
        : filename;
      return `${base}/wikipedia/commons/thumb/${path}/${stdWidth}px-${thumbFilename}`;
    }
  }

  if (imageUrl.includes("live.staticflickr.com/")) {
    return getFlickrThumbnailUrl(imageUrl, width);
  }

  return assetUrl(imageUrl);
}
/**
 * Filter and validate image data for display.
 * @param {Array} images - Array of image objects or URLs
 * @returns {Array} Valid image objects
 */
export function getValidImages(images) {
  if (!Array.isArray(images) || images.length === 0) return [];

  return images.filter((imageData) => {
    const url = typeof imageData === "string" ? imageData : imageData?.url;
    if (!url || typeof url !== "string") return false;

    // Filter out TIFF images (not supported by browsers)
    if (/\.tiff?(\?|$)/i.test(url)) return false;

    try {
      new URL(url);
      return true;
    } catch {
      return false;
    }
  });
}
/**
 * Extract a readable label from a source URL.
 * @param {string} url - Source URL
 * @returns {Object} {label, isWikipedia}
 */
export function sourceLabel(url) {
  try {
    const urlObj = new URL(url);
    const { hostname, pathname } = urlObj;

    // Handle Wikipedia URLs specially to extract article title
    if (hostname.includes("wikipedia.org")) {
      const match = pathname.match(/\/wiki\/(.+)/);
      if (match) {
        const title = decodeURIComponent(match[1])
          .replace(/_/g, " ")
          .replace(/#.*$/, "");
        return { label: title, isWikipedia: true };
      }
    }

    return { label: hostname.replace(/^www\./, ""), isWikipedia: false };
  } catch {
    return { label: url, isWikipedia: false };
  }
}
/**
 * Where a published work can be followed up, for a publication event.
 *
 * A resolved link comes from the data (`scripts/enrich_publication_links.py`
 * writes it after confirming both the title and the authorship against
 * Wikidata or Wikipedia). When there is none — the work has no record anywhere,
 * or the title the model wrote is a description rather than a name — the search
 * is built here instead: in the reader's language, so a German reader lands in
 * the German encyclopedia, and without ever going stale in the data.
 *
 * @param {Object|null} eventClass - The event's `event_class` block
 * @param {string|null} authorName - The story's subject, i.e. the work's author
 * @param {string} language - Current UI language code
 * @returns {{url: string, site: string, kind: string, isSearch: boolean}|null}
 */
export function getPublicationSource(eventClass, authorName, language = "en") {
  if (!eventClass || eventClass.type !== "publication") return null;

  const link = eventClass.source_link;
  if (link?.url) {
    return {
      url: link.url,
      site: link.site || sourceLabel(link.url).label,
      kind: link.kind || "link",
      isSearch: false,
    };
  }

  const title = (eventClass.title || "").trim();
  if (!title) return null;
  const host = /^[a-z]{2}$/.test(language || "")
    ? `${language}.wikipedia.org`
    : "en.wikipedia.org";
  const query = [title, authorName].filter(Boolean).join(" ");
  return {
    url: `https://${host}/w/index.php?search=${encodeURIComponent(query)}`,
    site: "Wikipedia",
    kind: "search",
    isSearch: true,
  };
}
/**
 * The pictures the depth layer shows: the ones searched for the background
 * report, and nothing else.
 *
 * The report's illustrations are searched against the report — the machine,
 * the building, the document it describes — so they show the reader something
 * the slide above did not. The event's own picture is deliberately not a
 * fallback: it is a screen up, the reader has just scrolled past it, and
 * reprinting it under the report is what made the layer look like a second
 * copy of the slide. A report with no illustrations is set as plain prose.
 * @param {Object} event - Event object
 * @returns {Array} Image objects with url and, where known, caption and credit
 */
export function getBackgroundImages(event) {
  if (!Array.isArray(event?.background_images)) return [];
  // The searches are told to leave the event's own pictures alone and the
  // candidate list drops them, but a picture that reached the reader twice —
  // once above the fold and once under it — is exactly what the layer is not
  // allowed to be, so the rule is held here as well as at generation.
  const onTheSlide = new Set(
    getValidImages(event?.images)
      .map((image) =>
        imageFileKey(typeof image === "string" ? image : image?.url)
      )
      .filter(Boolean)
  );
  const shown = new Set();
  return event.background_images.filter((image) => {
    const key = imageFileKey(image?.url);
    if (!key || onTheSlide.has(key) || shown.has(key)) return false;
    shown.add(key);
    return true;
  });
}

/**
 * A hosted image identified by the file it is, not by the size asked for.
 *
 * Commons serves the same file at any width, so the slide's copy and the
 * report's copy of one photograph differ only in a `640px-` prefix and a query
 * string. Comparing URLs would call them two pictures.
 * @param {string} url - Image URL
 * @returns {string} A key two sizes of the same file share
 */
function imageFileKey(url) {
  if (typeof url !== "string" || !url) return "";
  const name = decodeURIComponent(url.split("?")[0].split("/").pop() ?? "");
  return name.replace(/^\d+px-/, "").toLowerCase();
}

/**
 * Every picture in one story, in reading order, as the lightbox pages them.
 *
 * The portrait first, then each event's own picture followed by whatever
 * illustrates the report under it: a reader who opens a picture from the depth
 * layer arrives in the same gallery as one who opened it from a slide, next to
 * the pictures of the same event, rather than in a lightbox holding one image
 * with nowhere to page to.
 * @param {Object} portrait - The story's portrait, if it has one
 * @param {Array} eventSlides - Event slides in story order
 * @param {Map<number, number>} eventIndexToSlideIndex - Where each event sits
 * @returns {Array} Image objects carrying their event's identity
 */
export function collectStoryImages(
  portrait,
  eventSlides = [],
  eventIndexToSlideIndex = new Map()
) {
  const credited = (image) => ({
    url: image.url,
    caption: image.caption || null,
    source: image.source || null,
    creator: image.creator || null,
    license: image.license || null,
    licenseUrl: image.licenseUrl || null,
  });

  const images =
    portrait?.image || portrait?.full
      ? [
          {
            // Full-size for the viewer; the slide shows the thumbnail.
            ...credited({ ...portrait, url: portrait.full || portrait.image }),
            eventIndex: -1,
            eventTitle: null,
            eventDate: null,
            slideIndex: 0,
          },
        ]
      : [];

  for (const slide of eventSlides) {
    const slideIndex = eventIndexToSlideIndex.get(slide.eventIndex) ?? -1;
    const own = getValidImages(slide.images).map((image) =>
      typeof image === "string" ? { url: image } : image
    );
    for (const image of [...own, ...getBackgroundImages(slide)]) {
      images.push({
        ...credited(image),
        eventIndex: slide.eventIndex,
        eventTitle: slide.title,
        eventDate: slide.date,
        slideIndex,
      });
    }
  }

  return images;
}
