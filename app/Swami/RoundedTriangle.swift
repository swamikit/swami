import SwiftUI

/// An upward-pointing triangle with uniformly rounded corners.
///
/// Maps Origami's `builtin.layer.shape` when its path is a triangle carrying a
/// corner radius. SwiftUI ships no triangle primitive, so this fills the gap
/// faithfully rather than approximating with a rectangle: three vertices (apex
/// centered at the top, base along the bottom), each joined to its neighbours by
/// a quadratic arc so the corners round like Origami's shape layer.
///
/// `cornerRadius` is the inset applied along each edge from a vertex before the
/// arc begins; `0` yields a hard-cornered triangle.
public struct RoundedTriangle: Shape {
    public var cornerRadius: CGFloat

    public init(cornerRadius: CGFloat = 0) {
        self.cornerRadius = cornerRadius
    }

    public func path(in rect: CGRect) -> Path {
        // Apex on top, base along the bottom — matches the Origami shape's orientation.
        let vertices = [
            CGPoint(x: rect.midX, y: rect.minY),
            CGPoint(x: rect.maxX, y: rect.maxY),
            CGPoint(x: rect.minX, y: rect.maxY),
        ]
        let radius = max(0, cornerRadius)

        return Path { path in
            for index in vertices.indices {
                let current = vertices[index]
                let previous = vertices[(index + vertices.count - 1) % vertices.count]
                let next = vertices[(index + 1) % vertices.count]

                // Unit directions from this vertex toward each neighbour; the arc's
                // tangent points sit `radius` along those edges.
                let toPrevious = unitVector(from: current, to: previous)
                let toNext = unitVector(from: current, to: next)

                let arcStart = CGPoint(
                    x: current.x + toPrevious.dx * radius,
                    y: current.y + toPrevious.dy * radius
                )
                let arcEnd = CGPoint(
                    x: current.x + toNext.dx * radius,
                    y: current.y + toNext.dy * radius
                )

                if index == 0 {
                    path.move(to: arcStart)
                } else {
                    path.addLine(to: arcStart)
                }
                // Round the corner: the vertex is the control point of the arc.
                path.addQuadCurve(to: arcEnd, control: current)
            }
            path.closeSubpath()
        }
    }

    private func unitVector(from start: CGPoint, to end: CGPoint) -> CGVector {
        let dx = end.x - start.x
        let dy = end.y - start.y
        let length = max((dx * dx + dy * dy).squareRoot(), 0.0001)
        return CGVector(dx: dx / length, dy: dy / length)
    }
}
