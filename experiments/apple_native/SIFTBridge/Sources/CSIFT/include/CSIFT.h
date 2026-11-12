#ifndef PHOTO_NATIVE_SIFT_H
#define PHOTO_NATIVE_SIFT_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
// Opaque ownership: extraction allocates; exactly one destroy releases it.
typedef struct NPSIFTFeatures NPSIFTFeatures;
typedef struct {
    int32_t mutual_matches;
    int32_t inliers;
    double inlier_fraction;
    double coverage_a;
    double coverage_b;
    int32_t sift_candidate;
} NPSIFTResult;
const char *npsift_version(void);
int npsift_extract_rgba(const uint8_t *pixels, size_t length, int32_t width,
                       int32_t height, size_t stride, NPSIFTFeatures **output,
                       char *error, size_t error_capacity);
void npsift_destroy(NPSIFTFeatures *features);
int32_t npsift_count(const NPSIFTFeatures *features);
int npsift_compare(const NPSIFTFeatures *a, const NPSIFTFeatures *b,
                   NPSIFTResult *output, char *error, size_t error_capacity);
#ifdef __cplusplus
}
#endif
#endif
