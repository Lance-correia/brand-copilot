import Foundation
import Vision
import AppKit

struct Line: Codable {
    let text: String
    let confidence: Float
    let box: [Double]
    let angle: Double
}
let url = URL(fileURLWithPath: CommandLine.arguments[1])
let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.usesLanguageCorrection = false
let handler = VNImageRequestHandler(url: url, options: [:])
do { try handler.perform([request]) } catch {
    fputs("Local text recognition unavailable\n", stderr)
    exit(1)
}
let lines: [Line] = (request.results ?? []).compactMap { observation in
    guard let candidate = observation.topCandidates(1).first else { return nil }
    let b = observation.boundingBox
    return Line(text: candidate.string, confidence: candidate.confidence,
                box: [Double(b.minX), Double(1 - b.maxY), Double(b.maxX), Double(1 - b.minY)],
                angle: atan2(Double(observation.topRight.y - observation.topLeft.y), Double(observation.topRight.x - observation.topLeft.x)) * 180 / .pi)
}
let data = try JSONEncoder().encode(lines)
print(String(data: data, encoding: .utf8)!)
