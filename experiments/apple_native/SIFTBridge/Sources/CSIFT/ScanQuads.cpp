#include "CSIFT.h"
#include <opencv2/imgproc.hpp>
#include <algorithm>
#include <cmath>
#include <vector>

extern "C" int32_t np_scan_quads(const uint8_t *gray, int32_t width, int32_t height,
                                 int32_t polaroids, float *corners) {
    try {
        if (!gray || !corners || width < 8 || height < 8) return -1;
        cv::Mat image(height, width, CV_8UC1, const_cast<uint8_t *>(gray)), mask;
        if (polaroids) {
            cv::threshold(image, mask, 70, 255, cv::THRESH_BINARY);
        } else {
            std::vector<uint8_t> edge;
            for (int x = 0; x < width; ++x) {
                edge.push_back(image.at<uint8_t>(0, x));
                edge.push_back(image.at<uint8_t>(height - 1, x));
            }
            for (int y = 0; y < height; ++y) {
                edge.push_back(image.at<uint8_t>(y, 0));
                edge.push_back(image.at<uint8_t>(y, width - 1));
            }
            auto middle = edge.begin() + edge.size() / 2;
            std::nth_element(edge.begin(), middle, edge.end());
            const int background = *middle;
            const auto outliers = std::count_if(edge.begin(), edge.end(), [background](int x) {
                return std::abs(x - background) > 20;
            });
            if (outliers > edge.size() / 10) return -1;
            cv::absdiff(image, cv::Scalar(background), mask);
            cv::threshold(mask, mask, 25, 255, cv::THRESH_BINARY);
        }

        cv::morphologyEx(mask, mask, cv::MORPH_CLOSE, cv::getStructuringElement(cv::MORPH_RECT, {7, 7}));
        std::vector<std::vector<cv::Point>> contours;
        cv::findContours(mask, contours, cv::RETR_EXTERNAL, cv::CHAIN_APPROX_SIMPLE);
        int count = 0;
        for (const auto &contour : contours) {
            const auto box = cv::boundingRect(contour);
            const double area = cv::contourArea(contour);
            const double aspect = double(box.width) / box.height;
            if (area < double(width) * height * .015 || box.width < width * .10 || box.height < height * .08) continue;
            if (aspect < (polaroids ? .5 : .25) || aspect > (polaroids ? 2 : 4)) continue;
            const auto rectangle = cv::minAreaRect(contour);
            if (area < rectangle.size.area() * (polaroids ? .85 : .88) ||
                box.x <= 2 || box.y <= 2 || box.br().x >= width - 2 || box.br().y >= height - 2) return -1;
            if (count == 20) return -1;

            std::vector<cv::Point> polygon;
            cv::approxPolyDP(contour, polygon, .015 * cv::arcLength(contour, true), true);
            cv::Point2f points[4];
            if (polygon.size() == 4 && cv::isContourConvex(polygon)) {
                std::copy(polygon.begin(), polygon.end(), points);
            } else {
                rectangle.points(points);
            }
            const cv::Point2f center = (points[0] + points[1] + points[2] + points[3]) * .25f;
            std::sort(points, points + 4, [center](auto a, auto b) {
                return std::atan2(a.y - center.y, a.x - center.x) < std::atan2(b.y - center.y, b.x - center.x);
            });
            const auto first = std::min_element(points, points + 4, [](auto a, auto b) {
                return a.x + a.y < b.x + b.y;
            });
            std::rotate(points, first, points + 4);
            for (int i = 0; i < 4; ++i) {
                corners[8 * count + 2 * i] = points[i].x / width;
                corners[8 * count + 2 * i + 1] = points[i].y / height;
            }
            ++count;
        }
        return count;
    } catch (...) {
        return -1;
    }
}
