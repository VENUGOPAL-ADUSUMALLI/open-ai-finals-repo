
def tie_break_sort_key(result_row):
    job = result_row['job']
    return (
        -result_row['selection_probability'],
        -(result_row.get('published_at_ord') or 0),
        -(result_row.get('created_at_ord') or 0),
        str(job.job_id),
    )
