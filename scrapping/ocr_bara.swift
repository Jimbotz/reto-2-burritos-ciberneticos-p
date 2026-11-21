import Foundation
import Vision

struct Lectura: Encodable {
    let producto: String
    let importe_ocr: String?
}

let lecturas = CommandLine.arguments.dropFirst().map { path in
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.recognitionLanguages = ["es-MX"]
    let image = VNImageRequestHandler(url: URL(fileURLWithPath: path))
    do {
        try image.perform([request])
    } catch {
        return Lectura(producto: "", importe_ocr: nil)
    }
    let boxes = (request.results ?? []).sorted { $0.boundingBox.midY > $1.boundingBox.midY }
    let product = boxes.filter { $0.boundingBox.midY < 0.25 }
        .compactMap { $0.topCandidates(1).first?.string }
        .joined(separator: " ")
    let price = boxes.filter { (0.25...0.65).contains($0.boundingBox.midY) }
        .compactMap { $0.topCandidates(1).first?.string }
        .first { $0.hasPrefix("$") }
    return Lectura(producto: product, importe_ocr: price)
}

let json = try JSONEncoder().encode(lecturas)
FileHandle.standardOutput.write(json)
