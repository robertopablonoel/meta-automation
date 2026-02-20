"""
CLIP-based image embedding and clustering for visual sub-grouping.

Replaces the Claude vision sub-grouping pass with local CLIP embeddings
+ agglomerative clustering. Zero API calls, runs in ~30-50s for ~164 images.

Usage (called from pipeline.py):
    from image_embedder import cluster_images_by_visual_similarity
    subgroups = cluster_images_by_visual_similarity(image_paths, descriptions, ...)
"""

import hashlib
import logging
import re
from collections import Counter
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

# Words to exclude when generating sub-group names from descriptions
_STOP_WORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "shall", "can", "this", "that",
    "these", "those", "it", "its", "they", "them", "their", "we", "our",
    "you", "your", "he", "she", "his", "her", "image", "images", "ad",
    "creative", "creatives", "shows", "showing", "featuring", "features",
    "appears", "visible", "displayed", "background", "foreground", "text",
    "overlay", "overlays", "style", "various", "multiple", "single",
    "also", "very", "more", "most", "some", "all", "each", "every",
    "other", "such", "into", "over", "about", "up", "out", "off",
    "like", "just", "than", "then", "so", "no", "not", "only", "same",
}


def _cache_key(image_paths: list[Path]) -> str:
    """Generate a stable cache key from filenames + modification times."""
    parts = []
    for p in sorted(image_paths, key=lambda x: x.name):
        mtime = p.stat().st_mtime
        parts.append(f"{p.name}:{mtime}")
    raw = "|".join(parts)
    return hashlib.md5(raw.encode()).hexdigest()


def compute_embeddings(
    image_paths: list[Path],
    cache_dir: Path,
    model_name: str = "clip-ViT-B-32",
) -> np.ndarray:
    """Compute CLIP embeddings for all images, with disk caching.

    Returns an (N, D) array of L2-normalized embeddings.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = _cache_key(image_paths)
    cache_path = cache_dir / f"embeddings_{key}.npz"

    if cache_path.exists():
        data = np.load(cache_path)
        embeddings = data["embeddings"]
        cached_names = list(data["filenames"])
        current_names = [p.name for p in image_paths]
        if cached_names == current_names:
            logger.info(f"Loaded cached CLIP embeddings ({len(embeddings)} images)")
            return embeddings
        logger.info("Cache key matched but filenames differ, recomputing...")

    logger.info(f"Computing CLIP embeddings for {len(image_paths)} images (model: {model_name})...")

    from sentence_transformers import SentenceTransformer
    from PIL import Image

    model = SentenceTransformer(model_name)

    images = []
    for p in image_paths:
        img = Image.open(p).convert("RGB")
        images.append(img)

    embeddings = model.encode(images, batch_size=32, show_progress_bar=False)
    embeddings = np.array(embeddings, dtype=np.float32)

    # L2 normalize
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1, norms)
    embeddings = embeddings / norms

    # Cache
    np.savez(
        cache_path,
        embeddings=embeddings,
        filenames=np.array([p.name for p in image_paths]),
    )
    logger.info(f"Cached embeddings to {cache_path}")

    return embeddings


def cluster_embeddings(
    embeddings: np.ndarray,
    distance_threshold: float = 0.35,
    max_group_size: int = 10,
) -> list[list[int]]:
    """Cluster embeddings using agglomerative clustering on cosine distance.

    Returns a list of clusters, each a list of indices into the embeddings array.
    Oversized clusters (>max_group_size) are recursively re-clustered at a tighter threshold.
    """
    from sklearn.cluster import AgglomerativeClustering

    n = len(embeddings)
    if n <= 1:
        return [list(range(n))]

    # Cosine distance matrix
    similarity = embeddings @ embeddings.T
    similarity = np.clip(similarity, -1, 1)
    distance_matrix = 1.0 - similarity

    clustering = AgglomerativeClustering(
        n_clusters=None,
        distance_threshold=distance_threshold,
        linkage="average",
        metric="precomputed",
    )
    labels = clustering.fit_predict(distance_matrix)

    # Group indices by label
    clusters_dict: dict[int, list[int]] = {}
    for idx, label in enumerate(labels):
        clusters_dict.setdefault(label, []).append(idx)

    clusters = list(clusters_dict.values())

    # Recursively split oversized clusters
    final_clusters = []
    for cluster in clusters:
        if len(cluster) > max_group_size:
            sub_embeddings = embeddings[cluster]
            tighter_threshold = distance_threshold * 0.7
            sub_clusters = cluster_embeddings(
                sub_embeddings,
                distance_threshold=tighter_threshold,
                max_group_size=max_group_size,
            )
            for sc in sub_clusters:
                final_clusters.append([cluster[i] for i in sc])
        else:
            final_clusters.append(cluster)

    return final_clusters


def generate_subgroup_names(
    clusters: list[list[int]],
    image_paths: list[Path],
    descriptions: list[dict],
) -> list[dict]:
    """Generate descriptive names for each cluster using Pass 1 descriptions.

    Returns list of dicts with 'sub_group_name', 'reasoning', 'image_filenames'.
    """
    # Build filename -> description lookup
    desc_lookup = {d["image_filename"]: d for d in descriptions}

    results = []
    used_names = set()

    for cluster_idx, cluster in enumerate(clusters):
        filenames = [image_paths[i].name for i in cluster]

        # Collect visual keywords from descriptions
        word_counts = Counter()
        desc_snippets = []
        for fname in filenames:
            desc = desc_lookup.get(fname)
            if desc:
                visual = desc.get("visual_elements", "")
                tone = desc.get("emotional_tone", "")
                desc_snippets.append(f"{visual} ({tone})")
                # Tokenize and count meaningful words
                words = re.findall(r"[a-z]+", visual.lower())
                for w in words:
                    if w not in _STOP_WORDS and len(w) > 2:
                        word_counts[w] += 1

        # Pick top 4 keywords for the name
        top_words = [w for w, _ in word_counts.most_common(4)]
        if top_words:
            slug = "_".join(top_words)
        else:
            slug = f"group_{cluster_idx + 1}"

        # Ensure unique names
        base_slug = slug
        counter = 2
        while slug in used_names:
            slug = f"{base_slug}_{counter}"
            counter += 1
        used_names.add(slug)

        # Build reasoning from description snippets
        if desc_snippets:
            sample = desc_snippets[:3]
            reasoning = f"Cluster of {len(filenames)} visually similar images. Keywords: {', '.join(top_words[:4])}. Sample descriptions: {'; '.join(sample)}"
        else:
            reasoning = f"Cluster of {len(filenames)} visually similar images"

        results.append({
            "sub_group_name": slug,
            "reasoning": reasoning,
            "image_filenames": filenames,
        })

    return results


def cluster_images_by_visual_similarity(
    image_paths: list[Path],
    descriptions: list[dict],
    cache_dir: Path,
    model_name: str = "clip-ViT-B-32",
    distance_threshold: float = 0.35,
    max_group_size: int = 10,
) -> list[dict]:
    """Main entry point: embed, cluster, and name image sub-groups.

    Returns list of dicts matching the global_subgroups format:
        [{'sub_group_name': str, 'reasoning': str, 'image_filenames': [str, ...]}, ...]
    """
    if not image_paths:
        return []

    embeddings = compute_embeddings(image_paths, cache_dir, model_name)
    clusters = cluster_embeddings(embeddings, distance_threshold, max_group_size)
    subgroups = generate_subgroup_names(clusters, image_paths, descriptions)

    logger.info(f"CLIP clustering: {len(image_paths)} images -> {len(subgroups)} sub-groups")
    for sg in subgroups:
        logger.info(f"  {sg['sub_group_name']}: {len(sg['image_filenames'])} images")

    return subgroups
