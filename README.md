## Hanbury Campus Mapper

### Run

- **Option A (current)**:

```bash
python app.py
```

- **Option B (helper script)**:

```bash
chmod +x run.sh
./run.sh
```

### Notes

- Routes are saved with full drawn paths in `drawn_segments.coordinates` (JSON array of `{lat,lng}`).
- Segment endpoints + metadata are saved in `routes`.
- **Grade level** is only collected/stored when `userType === "student"`.

