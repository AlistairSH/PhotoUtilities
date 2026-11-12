#include "CSIFT.h"
#include <opencv2/core.hpp>
#include <opencv2/core/version.hpp>
#include <opencv2/imgproc.hpp>
#include <opencv2/features2d.hpp>
#include <opencv2/calib3d.hpp>
#include <algorithm>
#include <cstdio>
#include <exception>
#include <limits>
#include <memory>
#include <mutex>
#include <set>
#include <stdexcept>
#include <vector>

struct NPSIFTFeatures {
    std::vector<cv::KeyPoint> points;
    cv::Mat descriptors;
    int width, height;
};
namespace {
void message(char *buffer, size_t capacity, const char *text) noexcept {
    if (buffer && capacity) std::snprintf(buffer,capacity,"%s",text);
}
std::mutex geometryMutex;
struct RestoreRNG {
    uint64_t state = cv::theRNG().state;
    ~RestoreRNG() { cv::theRNG().state=state; }
};
double coverage(const std::vector<cv::Point2f> &points, int width, int height) {
    if (points.size()<3) return 0;
    std::vector<cv::Point2f> hull;
    cv::convexHull(points,hull);
    return cv::contourArea(hull)/(double(width)*height);
}
std::set<std::pair<int,int>> good(const cv::Mat &a,const cv::Mat &b,bool reverse) {
    cv::BFMatcher matcher(cv::NORM_L2);
    std::vector<std::vector<cv::DMatch>> rows;
    matcher.knnMatch(a,b,rows,2);
    std::set<std::pair<int,int>> selected;
    for (const auto &row:rows) if (row.size()==2 && double(row[0].distance)<.75*double(row[1].distance)) {
        selected.emplace(reverse ? row[0].trainIdx : row[0].queryIdx,
                         reverse ? row[0].queryIdx : row[0].trainIdx);
    }
    return selected;
}
}
extern "C" const char *npsift_version(void) { return CV_VERSION; }
extern "C" void npsift_destroy(NPSIFTFeatures *features) { delete features; }
extern "C" int32_t npsift_count(const NPSIFTFeatures *features) {
    return features ? static_cast<int32_t>(features->points.size()) : 0;
}
extern "C" int npsift_extract_rgba(const uint8_t *pixels,size_t length,int32_t width,
                                  int32_t height,size_t stride,NPSIFTFeatures **output,
                                  char *error,size_t capacity) {
    if (output) *output=nullptr;
    try {
        if (!pixels || !output || width<1 || height<1 || width>1024 || height>1024 ||
            stride<size_t(width)*4 || stride>std::numeric_limits<size_t>::max()/size_t(height) ||
            length<(size_t(height)-1)*stride+size_t(width)*4)
            throw std::invalid_argument("Expected bounded RGBA8 preview, dimensions 1...1024 and complete rows");
        auto result=std::make_unique<NPSIFTFeatures>();
        result->width=width; result->height=height;
        cv::Mat rgba(height,width,CV_8UC4,const_cast<uint8_t *>(pixels),stride), rgb, gray;
        cv::cvtColor(rgba,rgb,cv::COLOR_RGBA2RGB);
        cv::cvtColor(rgb,gray,cv::COLOR_RGB2GRAY);
        // Explicitly pinned accepted SIFT defaults; precise upscale stays disabled.
        cv::SIFT::create(500,3,.04,10,1.6,false)->detectAndCompute(gray,cv::noArray(),result->points,result->descriptors);
        *output=result.release();
        return 0;
    } catch (const std::exception &e) { message(error,capacity,e.what()); }
      catch (...) { message(error,capacity,"Unknown native extraction failure"); }
    return 1;
}
extern "C" int npsift_compare(const NPSIFTFeatures *a,const NPSIFTFeatures *b,
                              NPSIFTResult *output,char *error,size_t capacity) {
    if (output) *output={};
    try {
        if (!a || !b || !output) throw std::invalid_argument("Missing feature handle or output");
        if (a->descriptors.empty() || b->descriptors.empty() || std::min(a->points.size(),b->points.size())<2) return 0;
        auto forward=good(a->descriptors,b->descriptors,false), reverse=good(b->descriptors,a->descriptors,true);
        std::vector<std::pair<int,int>> mutual;
        std::set_intersection(forward.begin(),forward.end(),reverse.begin(),reverse.end(),std::back_inserter(mutual));
        output->mutual_matches=static_cast<int32_t>(mutual.size());
        if (mutual.size()<8) return 0;
        std::vector<cv::Point2f> source,target;
        for (const auto &pair:mutual) { source.push_back(a->points[pair.first].pt); target.push_back(b->points[pair.second].pt); }
        cv::Mat mask, matrix;
        {
            std::lock_guard<std::mutex> lock(geometryMutex);
            RestoreRNG restore;
            cv::setRNGSeed(0);
            matrix=cv::findHomography(source,target,cv::RANSAC,3.,mask,2000,.995);
        }
        if (matrix.empty() || mask.empty() || !cv::checkRange(matrix)) return 0;
        std::vector<cv::Point2f> selectedA,selectedB;
        for (size_t i=0;i<mutual.size();++i) if (mask.at<uint8_t>(static_cast<int>(i))) {
            selectedA.push_back(source[i]); selectedB.push_back(target[i]);
        }
        output->inliers=static_cast<int32_t>(selectedA.size());
        output->inlier_fraction=double(selectedA.size())/mutual.size();
        output->coverage_a=coverage(selectedA,a->width,a->height);
        output->coverage_b=coverage(selectedB,b->width,b->height);
        output->sift_candidate=output->inliers>=12 && output->inlier_fraction>=.5 &&
                               std::min(output->coverage_a,output->coverage_b)>=.1;
        return 0;
    } catch (const std::exception &e) { message(error,capacity,e.what()); }
      catch (...) { message(error,capacity,"Unknown native matching failure"); }
    return 1;
}
