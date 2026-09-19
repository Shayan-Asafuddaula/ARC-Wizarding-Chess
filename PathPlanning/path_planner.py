import chess

from robot_control import Robot


class Path:

    def __init__(self, piece: Robot, points: list) -> None:
        self.piece = piece
        self.points = points

    def __repr__(self):
        return f'{self.piece}: {self.points}'


def get_rank(square):
    if square <= 63:
        return chess.square_rank(square)

    elif square <= 79:
        # Black pieces (white side)
        return (square - 64) // 4

    else:
        # White pieces (black side)
        return 7 - (square - 80) // 4


def get_file(square):
    if square <= 63:
        return chess.square_file(square)

    elif square <= 79:
        # Black pieces (white side)
        return 11 - (square - 64) % 4

    else:
        # White pieces (black side)
        return 11 - (square - 80) % 4


class PathPlanner:

    def __init__(self, board: chess.Board) -> None:
        self.board = board

    def turn_paths(self, move: chess.Move) -> list[Path]:

        """
        Given a chess move, generate Paths in the order they
        should be traveled.

        Kiwi-drive version:
        - Robots can translate in any direction.
        - Normal moves therefore use a direct path.
        - Captures are handled in three stages:
            1. Capturing piece approaches captured piece.
            2. Captured piece leaves the board.
            3. Capturing piece moves into the captured piece's square.
        """

        paths = []

        if not self.board.is_legal(move):
            return False

        piece_id = self.board.piece_list[move.from_square]

        # ---------------------------------------------------------
        # CAPTURE
        # ---------------------------------------------------------

        if self.board.is_capture(move):

            captured_position = self.board.get_capture_position()

            # -----------------------------------------------------
            # EN PASSANT
            # -----------------------------------------------------

            if self.board.is_en_passant(move):

                captured_piece_square = (
                    move.to_square + (8 * self.board.turn)
                )

                captured_piece_id = (
                    self.board.piece_list[captured_piece_square]
                )

                # Capturing piece moves directly toward destination.
                paths.append(
                    Path(
                        piece_id,
                        self.single_path(
                            move.from_square,
                            move.to_square
                        )
                    )
                )

                # Captured pawn leaves the board.
                paths.append(
                    Path(
                        captured_piece_id,
                        self.single_path(
                            captured_piece_square,
                            captured_position,
                            move_type="LEAVE"
                        )
                    )
                )

                return paths

            # -----------------------------------------------------
            # NORMAL CAPTURE
            # -----------------------------------------------------

            captured_piece_id = (
                self.board.piece_list[move.to_square]
            )

            # Move capturing piece close to the target, but don't
            # drive directly through the captured robot.
            capture_path = self.single_path(
                move.from_square,
                move.to_square,
                move_type="CAPTURE"
            )

            obstructed_edge = -1

            # CAPTURE paths can begin with an edge indicator.
            if capture_path and isinstance(capture_path[0], int):
                obstructed_edge = capture_path[0]
                capture_path = capture_path[1:]

            paths.append(
                Path(
                    piece_id,
                    capture_path
                )
            )

            # Captured robot leaves the board.
            paths.append(
                Path(
                    captured_piece_id,
                    self.single_path(
                        move.to_square,
                        captured_position,
                        move_type="LEAVE",
                        obstructed_edge=obstructed_edge
                    )
                )
            )

            # Capturing robot moves into destination.
            paths.append(
                Path(
                    piece_id,
                    self.single_path(
                        move.to_square,
                        move.to_square
                    )
                )
            )

            return paths

        # ---------------------------------------------------------
        # CASTLING
        # ---------------------------------------------------------

        if self.board.is_castling(move):

            # King moves directly to its destination.
            paths.append(
                Path(
                    piece_id,
                    self.single_path(
                        move.from_square,
                        move.to_square
                    )
                )
            )

            rank = chess.square_rank(move.from_square)

            # -----------------------------------------------------
            # KINGSIDE
            # -----------------------------------------------------

            if self.board.is_kingside_castling(move):

                rook_square = chess.square(7, rank)

                rook_id = self.board.piece_list[rook_square]

                rook_target = chess.square(5, rank)

                paths.append(
                    Path(
                        rook_id,
                        self.single_path(
                            rook_square,
                            rook_target,
                            move_type="CASTLE"
                        )
                    )
                )

            # -----------------------------------------------------
            # QUEENSIDE
            # -----------------------------------------------------

            else:

                rook_square = chess.square(0, rank)

                rook_id = self.board.piece_list[rook_square]

                rook_target = chess.square(3, rank)

                # FIXED: original code accidentally used piece_id
                # here instead of rook_id.
                paths.append(
                    Path(
                        rook_id,
                        self.single_path(
                            rook_square,
                            rook_target,
                            move_type="CASTLE"
                        )
                    )
                )

            return paths

        # ---------------------------------------------------------
        # NORMAL MOVE
        # ---------------------------------------------------------

        paths.append(
            Path(
                piece_id,
                self.single_path(
                    move.from_square,
                    move.to_square
                )
            )
        )

        return paths

    def single_path(
        self,
        start: chess.Square,
        target: chess.Square,
        move_type="NORMAL",
        obstructed_edge=-1
    ) -> list[tuple]:

        """
        Generate movement points for a kiwi-drive robot.

        Kiwi drive can translate:
            - forward
            - backward
            - sideways
            - diagonally

        Therefore, unlike tank drive, most chess moves only need
        a direct start -> target path.

        Coordinates are the CENTER of each chess square.
        """

        start_rank = get_rank(start)
        start_file = get_file(start)

        end_rank = get_rank(target)
        end_file = get_file(target)

        # Center positions of squares.
        start_position = (
            start_file + 0.5,
            start_rank + 0.5
        )

        end_position = (
            end_file + 0.5,
            end_rank + 0.5
        )

        # =========================================================
        # NORMAL / KNIGHT / BISHOP / ROOK / QUEEN / KING
        # =========================================================

        if move_type == "NORMAL":

            return [
                start_position,
                end_position
            ]

        # =========================================================
        # CAPTURE
        # =========================================================

        elif move_type == "CAPTURE":

            change_in_rank = end_rank - start_rank
            change_in_file = end_file - start_file

            rank_direction = (
                1 if change_in_rank > 0 else
                -1 if change_in_rank < 0 else
                0
            )

            file_direction = (
                1 if change_in_file > 0 else
                -1 if change_in_file < 0 else
                0
            )

            # Approach the captured piece from the direction
            # the capturing piece is coming from.
            #
            # We stop one square-width away from the center.
            approach_position = (
                end_file + 0.5 - (file_direction * 0.5),
                end_rank + 0.5 - (rank_direction * 0.5)
            )

            # Determine whether the robot approaches from the
            # top/bottom edge of the board.
            edge = -1

            if rank_direction < 0:
                edge = 1
            elif rank_direction > 0:
                edge = 0

            return [
                edge,
                start_position,
                approach_position
            ]

        # =========================================================
        # CASTLING ROOK
        # =========================================================

        elif move_type == "CASTLE":

            return [
                start_position,
                end_position
            ]

        # =========================================================
        # PIECE LEAVING BOARD
        # =========================================================

        elif move_type == "LEAVE":

            change_in_rank = end_rank - start_rank
            change_in_file = end_file - start_file

            rank_direction = (
                1 if change_in_rank > 0 else
                -1 if change_in_rank < 0 else
                0
            )

            # Move the robot toward the edge first.
            #
            # For kiwi drive we don't need the complicated
            # stair-step movement used by the tank-drive version.

            leave_rank = start_rank

            if (
                rank_direction == 1
                and obstructed_edge != 1
            ):
                leave_rank += 1

            elif obstructed_edge == 0:
                leave_rank += 1

            leave_position = (
                start_file + 0.5,
                leave_rank + 0.5
            )

            # Move off the physical chessboard.
            exit_position = (
                end_file,
                leave_rank + 0.5
            )

            final_position = (
                end_file,
                end_rank + 0.5
            )

            return [
                start_position,
                leave_position,
                exit_position,
                final_position
            ]

        # =========================================================
        # UNKNOWN MOVE TYPE
        # =========================================================

        raise ValueError(
            f"Unknown move_type: {move_type}"
        )